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


def test_hard_filters_keep_all_same_brand_branches() -> None:
    config = load_data_collection_config(Path("config/data_collection.yaml")).discovery
    candidates = (
        candidate("starbucks-c", "Starbucks Ankara", "cafe", 300),
        candidate("starbucks-a", "Starbucks Eryaman", "cafe", 500),
        candidate("starbucks-b", "Starbucks Metromall", "cafe", 500),
        candidate("closed", "Closed Cafe", "cafe", 900, "CLOSED_PERMANENTLY"),
        candidate("small", "Small Cafe", "cafe", 40),
    )

    result = apply_hard_filters(candidates, config=config)

    # All three same-brand branches are kept; only status/review-count reject.
    assert [item.place_id for item in result.candidates] == [
        "starbucks-a",
        "starbucks-b",
        "starbucks-c",
    ]
    assert result.rejected_status == 1
    assert result.rejected_review_count == 1


def test_freshness_can_demote_a_stale_high_review_count_candidate() -> None:
    config = load_data_collection_config(Path("config/data_collection.yaml")).discovery
    today = date(2026, 7, 18)
    fresh = datetime(2026, 7, 17, tzinfo=UTC)
    stale = datetime.combine(
        today - timedelta(days=config.stale_after_days),
        datetime.min.time(),
        tzinfo=UTC,
    )
    raw = (
        candidate("popular-stale", "Popular Stale Place", "cafe", 1000),
        candidate("solid-fresh", "Solid Fresh Place", "cafe", 500),
        candidate("modest-fresh", "Modest Fresh Place", "cafe", 400),
    )

    # Preliminary (freshness-unknown) ranking favors raw review count alone;
    # this is what freshness_shortlist must NOT lock in as the final pool
    # before a real freshness check happens (that was the bug).
    preliminary = tuple(
        score_candidate(item, newest_review_at=None, as_of_date=today, config=config)
        for item in raw
    )
    preliminary_top_two = [
        item.candidate.place_id
        for item in sorted(preliminary, key=lambda i: (-i.score, i.candidate.place_id))
    ][:2]
    assert preliminary_top_two == ["popular-stale", "solid-fresh"]

    # Once real freshness is known, the stale-but-popular candidate must be
    # out-ranked by the fresher, lower-review-count spare -- which requires
    # the spare (modest-fresh) to still be in the candidate pool at this
    # point, i.e. the pool passed to selection must exceed target_count.
    scored = tuple(
        score_candidate(
            item,
            newest_review_at=stale if item.place_id == "popular-stale" else fresh,
            as_of_date=today,
            config=config,
        )
        for item in raw
    )

    selected = select_candidates(scored, existing=(), target_count=2)

    assert [item.candidate.place_id for item in selected] == [
        "solid-fresh",
        "modest-fresh",
    ]


def test_selection_ranks_by_freshness_score_and_place_id_tie_breaker() -> None:
    base_config = load_data_collection_config(
        Path("config/data_collection.yaml")
    ).discovery
    config = base_config.model_copy(update={"target_count": 4})
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

    selected = select_candidates(scored, existing=(), target_count=4)

    # rest-stale still outranks everything despite the freshness penalty
    # (huge review count); cafe-a/cafe-b tie on score and split on place_id;
    # rest-b (lowest review count) misses the top-4 cut.
    assert [item.candidate.place_id for item in selected] == [
        "rest-stale",
        "cafe-a",
        "cafe-b",
        "rest-a",
    ]


def test_expansion_preserves_existing_catalog_entry() -> None:
    base_config = load_data_collection_config(
        Path("config/data_collection.yaml")
    ).discovery
    config = base_config.model_copy(update={"target_count": 2})
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

    selected = select_candidates(scored, existing=existing, target_count=2)

    assert [item.candidate.place_id for item in selected] == ["rest-a"]
