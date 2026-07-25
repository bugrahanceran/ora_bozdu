from datetime import UTC, date, datetime
from pathlib import Path

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalog, VenueCatalogEntry
from app.data_collection_config import load_data_collection_config
from app.services.discovery_service import build_discovery_result

CONFIG_PATH = Path("config/data_collection.eryaman.yaml")


def _candidate(place_id: str, display_name: str, category: str) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        place_id=place_id,
        display_name=display_name,
        category=category,
        business_status="OPERATIONAL",
        user_ratings_total=500,
        primary_type=category,
        latitude=39.979,
        longitude=32.636,
    )


def test_build_discovery_result_adds_every_eligible_candidate_take_all() -> None:
    # No target_count to compete over: every candidate that passes hard
    # filters and has a freshness result gets added, however many there are.
    config = load_data_collection_config(CONFIG_PATH)
    existing = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    searched = (
        _candidate("cafe-place", "Fixture Cafe", "cafe"),
        _candidate("restaurant-place", "Fixture Restaurant", "restaurant"),
        _candidate("bakery-place", "Fixture Bakery", "bakery"),
    )
    freshness = {
        candidate.place_id: datetime(2026, 7, 17, tzinfo=UTC) for candidate in searched
    }

    result = build_discovery_result(
        config=config,
        existing_catalog=existing,
        as_of_date=date(2026, 7, 18),
        searched=searched,
        grid_summary={"total_cells": 9},
        freshness_by_place_id=freshness,
        all_scanned_candidates=searched,
    )

    assert len(result.catalog.venues) == 3
    assert {entry.place_id for entry in result.catalog.venues} == {
        "cafe-place",
        "restaurant-place",
        "bakery-place",
    }
    assert result.report["added_count"] == 3
    assert result.report["rejected"]["duplicate_or_existing"] == 0
    # All three fit well within tracked_venue_limit (200), so all get tracked.
    assert result.report["tracked_count"] == 3
    assert result.report["not_tracked_count"] == 0
    assert all(entry.tracked for entry in result.catalog.venues)
    assert all(entry.user_ratings_total == 500 for entry in result.catalog.venues)


def test_build_discovery_result_preserves_existing_and_skips_duplicates() -> None:
    config = load_data_collection_config(CONFIG_PATH)
    existing = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="existing-cafe",
                display_name="Existing Cafe",
                place_id="existing-place",
                category="cafe",
                brand_key="existing-cafe",
            ),
        ),
    )
    # One brand-new candidate plus one that duplicates an already-catalogued
    # place_id (e.g. re-discovered on a repeat grid sweep).
    new_candidate = _candidate("new-place", "New Restaurant", "restaurant")
    duplicate_candidate = _candidate("existing-place", "Existing Cafe", "cafe")
    searched = (new_candidate, duplicate_candidate)

    result = build_discovery_result(
        config=config,
        existing_catalog=existing,
        as_of_date=date(2026, 7, 18),
        searched=searched,
        grid_summary={"total_cells": 9},
        freshness_by_place_id={"new-place": datetime(2026, 7, 17, tzinfo=UTC)},
        all_scanned_candidates=searched,
    )

    assert {entry.place_id for entry in result.catalog.venues} == {
        "existing-place",
        "new-place",
    }
    assert result.report["existing_preserved"] == 1
    assert result.report["added_count"] == 1
    assert result.report["rejected"]["duplicate_or_existing"] == 1
    # The re-discovered "existing-place" gets its review count refreshed
    # from this round's scan even though it was already catalogued.
    by_id = {entry.place_id: entry for entry in result.catalog.venues}
    assert by_id["existing-place"].user_ratings_total == 500


def test_build_discovery_result_untracks_the_lowest_ranked_when_over_limit() -> None:
    config = load_data_collection_config(CONFIG_PATH)
    limited_discovery = config.discovery.model_copy(update={"tracked_venue_limit": 2})
    config = config.model_copy(update={"discovery": limited_discovery})
    existing = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    searched = (
        _candidate("top", "Top Place", "cafe"),
        _candidate("mid", "Mid Place", "cafe"),
        _candidate("low", "Low Place", "cafe"),
    )
    freshness = {
        candidate.place_id: datetime(2026, 7, 17, tzinfo=UTC) for candidate in searched
    }

    result = build_discovery_result(
        config=config,
        existing_catalog=existing,
        as_of_date=date(2026, 7, 18),
        searched=searched,
        grid_summary={"total_cells": 9},
        freshness_by_place_id=freshness,
        all_scanned_candidates=searched,
    )

    assert result.report["tracked_count"] == 2
    assert result.report["not_tracked_count"] == 1
    # All three candidates tie on review count (500, via the _candidate
    # helper); rank_tracked_venues breaks ties by place_id ascending, so
    # "top" (alphabetically last of the three) loses the tie.
    by_id = {entry.place_id: entry for entry in result.catalog.venues}
    assert by_id["low"].tracked is True
    assert by_id["mid"].tracked is True
    assert by_id["top"].tracked is False
