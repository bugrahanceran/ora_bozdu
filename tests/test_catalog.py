from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import (
    VenueCatalog,
    VenueCatalogEntry,
    load_catalog,
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
        ),
    )

    write_catalog(path, catalog)

    assert load_catalog(path) == catalog
    assert "Fixture Cafe" in path.read_text(encoding="utf-8")


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
