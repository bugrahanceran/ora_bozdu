from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalogEntry
from app.data_collection_config import load_data_collection_config
from app.discovery.selector import (
    accept_all_candidates,
    apply_hard_filters,
    rank_tracked_venues,
    score_candidate,
)

CONFIG_PATH = Path("config/data_collection.eryaman.yaml")
REGION_CENTER_LATITUDE = 39.979
REGION_CENTER_LONGITUDE = 32.636


def candidate(
    place_id: str,
    name: str,
    category: str,
    count: int,
    status: str = "OPERATIONAL",
    *,
    latitude: float = REGION_CENTER_LATITUDE,
    longitude: float = REGION_CENTER_LONGITUDE,
) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        place_id=place_id,
        display_name=name,
        category=category,
        business_status=status,
        user_ratings_total=count,
        primary_type=category,
        latitude=latitude,
        longitude=longitude,
    )


def test_hard_filters_keep_all_same_brand_branches() -> None:
    config = load_data_collection_config(CONFIG_PATH)
    candidates = (
        candidate("starbucks-c", "Starbucks Ankara", "cafe", 300),
        candidate("starbucks-a", "Starbucks Eryaman", "cafe", 500),
        candidate("starbucks-b", "Starbucks Metromall", "cafe", 500),
        candidate("closed", "Closed Cafe", "cafe", 900, "CLOSED_PERMANENTLY"),
        candidate("small", "Small Cafe", "cafe", 40),
    )

    result = apply_hard_filters(
        candidates, config=config.discovery, region=config.region
    )

    # All three same-brand branches are kept; only status/review-count reject.
    assert [item.place_id for item in result.candidates] == [
        "starbucks-a",
        "starbucks-b",
        "starbucks-c",
    ]
    assert result.rejected_status == 1
    assert result.rejected_review_count == 1
    assert result.rejected_outside_radius == 0


def test_hard_filters_reject_candidates_outside_the_region_radius() -> None:
    config = load_data_collection_config(CONFIG_PATH)
    # A grid cell near the region boundary can return a place slightly beyond
    # radius_meters (the circumscribed-circle overshoot); this must be caught
    # here so radius_meters keeps a precise meaning.
    far_away = candidate(
        "far",
        "Far Cafe",
        "cafe",
        500,
        latitude=REGION_CENTER_LATITUDE + 1.0,
        longitude=REGION_CENTER_LONGITUDE,
    )
    nearby = candidate("near", "Near Cafe", "cafe", 500)

    result = apply_hard_filters(
        (far_away, nearby), config=config.discovery, region=config.region
    )

    assert [item.place_id for item in result.candidates] == ["near"]
    assert result.rejected_outside_radius == 1


def test_hard_filters_reject_irrelevant_primary_types() -> None:
    # Nearby Search's includedTypes matches any of a place's type tags, not
    # just its primaryType, so a hair salon or supermarket that also carries
    # a secondary food-adjacent tag can slip into results. These are
    # rejected locally by primaryType so freshness is never wasted on them.
    config = load_data_collection_config(CONFIG_PATH)
    irrelevant = candidate("salon", "Kuaför Güzellik", "hair_salon", 500)
    relevant = candidate("cafe-a", "Real Cafe", "cafe", 500)

    result = apply_hard_filters(
        (irrelevant, relevant), config=config.discovery, region=config.region
    )

    assert [item.place_id for item in result.candidates] == ["cafe-a"]
    assert result.rejected_irrelevant_primary_type == 1


def test_accept_all_candidates_includes_everyone_regardless_of_score() -> None:
    config = load_data_collection_config(CONFIG_PATH).discovery
    today = date(2026, 7, 18)
    fresh = datetime(2026, 7, 17, tzinfo=UTC)
    stale = datetime.combine(
        today - timedelta(days=config.stale_after_days),
        datetime.min.time(),
        tzinfo=UTC,
    )
    raw = (
        candidate("popular-stale", "Popular Stale Place", "cafe", 1000),
        candidate("modest-fresh", "Modest Fresh Place", "cafe", 60),
    )
    scored = tuple(
        score_candidate(
            item,
            newest_review_at=stale if item.place_id == "popular-stale" else fresh,
            as_of_date=today,
            config=config,
        )
        for item in raw
    )

    added = accept_all_candidates(scored)

    # No target_count to compete over: a popular-but-stale place and a modest
    # fresh one are both added, nothing is discarded as "not selected".
    assert {item.candidate.place_id for item in added} == {
        "popular-stale",
        "modest-fresh",
    }


def catalog_entry(
    place_id: str,
    *,
    tracked: bool = True,
    user_ratings_total: int | None = None,
) -> VenueCatalogEntry:
    return VenueCatalogEntry(
        slug=place_id,
        display_name=place_id,
        place_id=place_id,
        category="cafe",
        brand_key=place_id,
        tracked=tracked,
        user_ratings_total=user_ratings_total,
    )


def test_rank_tracked_venues_marks_top_limit_tracked_and_rest_untracked() -> None:
    entries = (
        catalog_entry("a"),
        catalog_entry("b"),
        catalog_entry("c"),
        catalog_entry("d", tracked=True, user_ratings_total=150),
    )
    # "d" isn't in this round's scan (e.g. outside this round's grid sweep)
    # but keeps its last-known count of 150 as a ranking fallback.
    current_review_counts = {"a": 300, "b": 200, "c": 100}

    ranked = rank_tracked_venues(
        entries, current_review_counts=current_review_counts, limit=2
    )

    by_id = {item.place_id: item for item in ranked}
    assert by_id["a"].tracked is True
    assert by_id["b"].tracked is True
    assert by_id["d"].tracked is False  # outranked despite being tracked before
    assert by_id["c"].tracked is False
    assert by_id["d"].user_ratings_total == 150
    # Original list order is preserved, not re-sorted by rank.
    assert [item.place_id for item in ranked] == ["a", "b", "c", "d"]


def test_rank_tracked_venues_leaves_entries_with_no_known_count_untouched() -> None:
    entries = (
        catalog_entry("known-a", tracked=False),
        catalog_entry("known-b", tracked=False),
        catalog_entry("never-scanned", tracked=True),
    )
    # "never-scanned" has no count this round and never had one before --
    # there's nothing to rank it by, so ranking must leave its existing
    # tracked flag alone rather than silently untracking it for lack of data.
    current_review_counts = {"known-a": 900, "known-b": 800}

    ranked = rank_tracked_venues(
        entries, current_review_counts=current_review_counts, limit=1
    )

    by_id = {item.place_id: item for item in ranked}
    assert by_id["known-a"].tracked is True
    assert by_id["known-b"].tracked is False
    assert by_id["never-scanned"].tracked is True
    assert by_id["never-scanned"].user_ratings_total is None


def test_rank_tracked_venues_demotes_incumbent_when_a_rival_grows() -> None:
    entries = (
        catalog_entry("incumbent", tracked=True, user_ratings_total=120),
        catalog_entry("challenger", tracked=False, user_ratings_total=90),
    )
    # This round's scan shows the challenger overtook the incumbent's review
    # count -- tracking must follow the data every cycle, not stay pinned to
    # whoever was tracked last time.
    current_review_counts = {"incumbent": 130, "challenger": 400}

    ranked = rank_tracked_venues(
        entries, current_review_counts=current_review_counts, limit=1
    )

    by_id = {item.place_id: item for item in ranked}
    assert by_id["challenger"].tracked is True
    assert by_id["challenger"].user_ratings_total == 400
    assert by_id["incumbent"].tracked is False
    assert by_id["incumbent"].user_ratings_total == 130


def test_accept_all_candidates_orders_by_score_then_place_id() -> None:
    config = load_data_collection_config(CONFIG_PATH).discovery
    today = date(2026, 7, 18)
    fresh = datetime(2026, 7, 17, tzinfo=UTC)
    raw = (
        candidate("cafe-b", "Cafe B", "cafe", 1000),
        candidate("cafe-a", "Cafe A", "cafe", 1000),
        candidate("rest-a", "Rest A", "restaurant", 300),
    )
    scored = tuple(
        score_candidate(item, newest_review_at=fresh, as_of_date=today, config=config)
        for item in raw
    )

    added = accept_all_candidates(scored)

    # cafe-a/cafe-b tie on score (identical review count) and split on
    # place_id; rest-a's lower review count ranks it last.
    assert [item.candidate.place_id for item in added] == [
        "cafe-a",
        "cafe-b",
        "rest-a",
    ]
