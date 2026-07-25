from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import (
    VenueCatalog,
    VenueCatalogEntry,
    load_catalog,
    load_other_region_place_ids,
    sync_catalog,
    write_catalog,
)
from app.models import Venue


def test_catalog_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "catalog.yaml"
    catalog = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="fixture-cafe",
                display_name="Fixture Cafe",
                place_id="place-1",
                category="cafe",
                brand_key="fixture-cafe",
            ),
            VenueCatalogEntry(
                slug="not-tracked-cafe",
                display_name="Not Tracked Cafe",
                place_id="place-2",
                category="cafe",
                brand_key="not-tracked-cafe",
                tracked=False,
                user_ratings_total=42,
            ),
        ),
    )

    write_catalog(path, catalog)

    assert load_catalog(path) == catalog
    assert "Fixture Cafe" in path.read_text(encoding="utf-8")


def test_load_catalog_defaults_tracked_true_for_older_files_without_it(
    tmp_path: Path,
) -> None:
    path = tmp_path / "catalog.yaml"
    path.write_text(
        "version: catalog.v1\n"
        "region:\n  slug: eryaman\n  name: Eryaman\n"
        "venues:\n"
        "  - slug: fixture-cafe\n"
        "    display_name: Fixture Cafe\n"
        "    place_id: place-1\n"
        "    category: cafe\n"
        "    brand_key: fixture-cafe\n",
        encoding="utf-8",
    )

    catalog = load_catalog(path)

    assert catalog.venues[0].tracked is True
    assert catalog.venues[0].user_ratings_total is None


def test_load_other_region_place_ids_unions_sibling_catalogs(tmp_path: Path) -> None:
    eryaman_path = tmp_path / "catalog.eryaman.yaml"
    armada_path = tmp_path / "catalog.armada.yaml"
    write_catalog(
        eryaman_path,
        VenueCatalog(
            region_slug="eryaman",
            region_name="Eryaman",
            venues=(
                VenueCatalogEntry(
                    slug="eryaman-cafe",
                    display_name="Eryaman Cafe",
                    place_id="eryaman-place",
                    category="cafe",
                    brand_key="eryaman-cafe",
                ),
            ),
        ),
    )
    write_catalog(
        armada_path,
        VenueCatalog(
            region_slug="armada",
            region_name="Armada",
            venues=(
                VenueCatalogEntry(
                    slug="armada-cafe",
                    display_name="Armada Cafe",
                    place_id="armada-place",
                    category="cafe",
                    brand_key="armada-cafe",
                ),
            ),
        ),
    )

    from_eryaman = load_other_region_place_ids(
        eryaman_path, current_region_slug="eryaman"
    )
    from_armada = load_other_region_place_ids(armada_path, current_region_slug="armada")

    assert from_eryaman == frozenset({"armada-place"})
    assert from_armada == frozenset({"eryaman-place"})


def test_catalog_is_source_of_truth_for_active_db_venues(session: Session) -> None:
    initial = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="old-cafe",
                display_name="Old Cafe",
                place_id="old-place",
                category="cafe",
                brand_key="old-cafe",
            ),
        ),
    )
    sync_catalog(session, initial)

    replacement = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="new-cafe",
                display_name="New Cafe",
                place_id="new-place",
                category="cafe",
                brand_key="new-cafe",
            ),
        ),
    )
    sync_catalog(session, replacement)

    venues = {
        venue.slug: venue
        for venue in session.scalars(select(Venue).order_by(Venue.slug)).all()
    }
    assert venues["old-cafe"].is_active is False
    assert venues["new-cafe"].is_active is True


def test_catalog_is_source_of_truth_for_tracked_db_venues(session: Session) -> None:
    initial = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="popular-cafe",
                display_name="Popular Cafe",
                place_id="popular-place",
                category="cafe",
                brand_key="popular-cafe",
                tracked=True,
            ),
        ),
    )
    sync_catalog(session, initial)

    # A later discovery cycle demotes the venue out of the top-N.
    demoted = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="popular-cafe",
                display_name="Popular Cafe",
                place_id="popular-place",
                category="cafe",
                brand_key="popular-cafe",
                tracked=False,
            ),
        ),
    )
    sync_catalog(session, demoted)

    venue = session.scalar(select(Venue).where(Venue.slug == "popular-cafe"))
    assert venue is not None
    assert venue.is_tracked is False
