from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalogEntry
from app.data_collection_config import load_data_collection_config
from app.discovery.selector import (
    apply_hard_filters,
    score_candidate,
    select_candidates,
)


def candidate(
    place_id: str,
    name: str,
    category: str,
    count: int,
    status: str = "OPERATIONAL",
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        place_id=place_id,
        display_name=name,
        category=category,
        business_status=status,
        user_ratings_total=count,
        primary_type=category,
    )


def test_hard_filters_and_brand_cap_are_deterministic() -> None:
    config = load_data_collection_config(Path("config/data_collection.yaml")).discovery
    candidates = (
        candidate("starbucks-c", "Starbucks Ankara", "cafe", 300),
        candidate("starbucks-a", "Starbucks Eryaman", "cafe", 500),
        candidate("starbucks-b", "Starbucks Metromall", "cafe", 500),
        candidate("closed", "Closed Cafe", "cafe", 900, "CLOSED_PERMANENTLY"),
        candidate("small", "Small Cafe", "cafe", 99),
    )

    result = apply_hard_filters(candidates, config=config, existing=())

    assert [item.place_id for item in result.candidates] == [
        "starbucks-a",
        "starbucks-b",
    ]
    assert result.rejected_status == 1
    assert result.rejected_review_count == 1
    assert result.rejected_brand_cap == 1


def test_selection_uses_quotas_freshness_and_place_id_tie_breaker() -> None:
    base_config = load_data_collection_config(
        Path("config/data_collection.yaml")
    ).discovery
    config = base_config.model_copy(
        update={"target_count": 4, "category_minimums": {"cafe": 1, "restaurant": 2}}
    )
    today = date(2026, 7, 18)
    fresh = datetime(2026, 7, 17, tzinfo=UTC)
    stale = datetime.combine(
        today - timedelta(days=config.stale_after_days),
        datetime.min.time(),
        tzinfo=UTC,
    )
    raw = (
        candidate("cafe-b", "Cafe B", "cafe", 1000),
        candidate("cafe-a", "Cafe A", "cafe", 1000),
        candidate("rest-a", "Rest A", "restaurant", 300),
        candidate("rest-b", "Rest B", "restaurant", 250),
        candidate("rest-stale", "Rest Stale", "restaurant", 5000),
    )
    scored = tuple(
        score_candidate(
            item,
            newest_review_at=stale if item.place_id == "rest-stale" else fresh,
            as_of_date=today,
            config=config,
        )
        for item in raw
    )

    selected = select_candidates(
        scored,
        existing=(),
        target_count=4,
        config=config,
    )

    selected_ids = [item.candidate.place_id for item in selected]
    assert selected_ids[:3] == ["cafe-a", "rest-stale", "rest-a"]
    assert selected_ids[3] == "cafe-b"


def test_expansion_preserves_existing_catalog_entry() -> None:
    base_config = load_data_collection_config(
        Path("config/data_collection.yaml")
    ).discovery
    config = base_config.model_copy(
        update={"target_count": 2, "category_minimums": {"cafe": 1, "restaurant": 1}}
    )
    existing = (
        VenueCatalogEntry(
            slug="existing-cafe",
            display_name="Existing Cafe",
            place_id="existing",
            category="cafe",
            brand_key="existing-cafe",
        ),
    )
    item = candidate("rest-a", "Rest A", "restaurant", 500)
    scored = (
        score_candidate(
            item,
            newest_review_at=datetime(2026, 7, 17, tzinfo=UTC),
            as_of_date=date(2026, 7, 18),
            config=config,
        ),
    )

    selected = select_candidates(
        scored,
        existing=existing,
        target_count=2,
        config=config,
    )

    assert [item.candidate.place_id for item in selected] == ["rest-a"]
