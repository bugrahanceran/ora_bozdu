from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.backfill import (
    APIFY_ACTOR,
    APIFY_USD_PER_1000,
    DEFAULT_REVIEWS_LIMIT,
    _fetch_plan,
    parse_apify_review,
    persist_reviews,
    persist_snapshots,
)
from app.catalog import VenueCatalog, VenueCatalogEntry
from app.models import FetchRunWarning, PlaceSnapshot, VenueReview


def _catalog() -> VenueCatalog:
    return VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="tracked-cafe",
                display_name="Tracked Cafe",
                place_id="ChIJtracked",
                category="cafe",
                brand_key="tracked-cafe",
                tracked=True,
            ),
            VenueCatalogEntry(
                slug="untracked-cafe",
                display_name="Untracked Cafe",
                place_id="ChIJuntracked",
                category="cafe",
                brand_key="untracked-cafe",
                tracked=False,
            ),
        ),
    )


def _review(
    review_id: str,
    *,
    place_id: str = "ChIJtracked",
    published: str = "2025-07-01T10:00:00.000Z",
    stars: int = 4,
    text: str = "taze ve güzel",
) -> dict:
    return {
        "reviewId": review_id,
        "placeId": place_id,
        "name": "Ayşe",
        "stars": stars,
        "text": text,
        "publishedAtDate": published,
    }


def test_fetch_plan_counts_tracked_venues_and_cost() -> None:
    plan = _fetch_plan(
        _catalog(),
        reviews_limit=50,
        lookback_days=365,
        snapshot_date=date(2026, 7, 25),
        cadence="weekly",
        week_start="monday",
        anchor_date=None,
    )

    assert plan["actor"] == APIFY_ACTOR
    assert plan["produces"] == "place_snapshots + venue_reviews + v6 recompute"
    assert plan["tracked_venues"] == 1  # only the tracked one
    assert plan["reviews_limit_per_venue"] == 50
    assert plan["reviews_start_date"] == "365 days"
    assert plan["cadence"] == "weekly"
    assert plan["snapshot_date"] == "2026-07-25"
    assert "period_start" in plan
    assert plan["apify_runs"] == 1
    assert plan["estimated_max_reviews"] == 50
    # 50 reviews at ~$0.30/1000 -> a couple of cents.
    expected_cost = 50 / 1000 * APIFY_USD_PER_1000
    assert plan["estimated_cost_usd_max"] == pytest.approx(expected_cost)


def test_default_reviews_limit_is_fifty() -> None:
    assert DEFAULT_REVIEWS_LIMIT == 50


def test_parse_apify_review_reads_date_rating_and_text() -> None:
    parsed = parse_apify_review(
        _review("r1", published="2025-07-01T10:00:00.000Z", stars=4, text="taze")
    )

    assert parsed is not None
    assert parsed.rating == 4
    assert parsed.text == "taze"
    assert parsed.provider_review_id == "r1"
    assert parsed.published_at.date() == date(2025, 7, 1)
    assert parsed.published_at.tzinfo is not None


def test_parse_apify_review_accepts_date_only_string() -> None:
    parsed = parse_apify_review(
        {"reviewId": "r2", "stars": 5, "text": "x", "publishedAtDate": "2021-07-26"}
    )

    assert parsed is not None
    assert parsed.published_at.date() == date(2021, 7, 26)
    assert parsed.published_at.tzinfo is not None


def test_parse_apify_review_skips_dateless_or_unrated() -> None:
    assert parse_apify_review({"stars": 5, "text": "x"}) is None
    assert (
        parse_apify_review(
            {"stars": 0, "text": "x", "publishedAtDate": "2025-07-01T10:00:00.000Z"}
        )
        is None
    )


def test_parse_apify_review_extracts_detailed_rating() -> None:
    parsed = parse_apify_review(
        {
            "reviewId": "r1",
            "stars": 5,
            "text": "x",
            "publishedAtDate": "2025-07-01T10:00:00.000Z",
            "reviewDetailedRating": {"Food": 5, "Service": 4, "Atmosphere": 5},
        }
    )

    assert parsed is not None
    assert parsed.sub_ratings == {"Food": 5, "Service": 4, "Atmosphere": 5}


def test_parse_apify_review_empty_detailed_rating_is_none() -> None:
    parsed = parse_apify_review(
        {
            "reviewId": "r2",
            "stars": 5,
            "text": "x",
            "publishedAtDate": "2025-07-01T10:00:00.000Z",
            "reviewDetailedRating": {},
        }
    )

    assert parsed is not None
    assert parsed.sub_ratings is None


def test_persist_joins_on_place_id_skips_unknown_and_is_idempotent(
    session: Session,
) -> None:
    catalog = _catalog()
    items = [
        _review("a", place_id="ChIJtracked", stars=5, text="taze"),
        _review("b", place_id="ChIJtracked", stars=2, text="pahalı"),
        _review("c", place_id="ChIJunknown", stars=4, text="x"),
    ]

    first = persist_reviews(session, items=items, catalog=catalog)
    assert first["added"] == 2
    assert first["venues_with_reviews"] == 1
    assert first["unmatched_place_ids"] == ["ChIJunknown"]

    # Re-importing the same response updates in place -- no duplicates.
    second = persist_reviews(session, items=items, catalog=catalog)
    assert second["added"] == 0
    assert second["updated"] == 2
    assert session.scalar(select(func.count(VenueReview.id))) == 2
    assert {row.source for row in session.scalars(select(VenueReview))} == {"backfill"}


def test_persist_handles_singly_nested_lists(session: Session) -> None:
    # Guard the defensive one-level unwrap in _iter_reviews.
    catalog = _catalog()
    items = [[_review("a", place_id="ChIJtracked", stars=5, text="iyi")]]

    summary = persist_reviews(session, items=items, catalog=catalog)

    assert summary["added"] == 1


def test_persist_stores_sub_ratings(session: Session) -> None:
    catalog = _catalog()
    item = _review("a", place_id="ChIJtracked", stars=4, text="x")
    item["reviewDetailedRating"] = {"Food": 4, "Service": 3}

    persist_reviews(session, items=[item], catalog=catalog)

    row = session.scalars(select(VenueReview)).one()
    assert row.sub_ratings == {"Food": 4, "Service": 3}


def _place_item(
    place_id: str = "ChIJtracked",
    *,
    title: str = "Tracked Cafe",
    total_score: float = 4.5,
    reviews_count: int = 1200,
    review_id: str = "a",
    published: str = "2025-07-01T10:00:00.000Z",
) -> dict:
    item = _review(review_id, place_id=place_id, stars=5, text="x")
    item["publishedAtDate"] = published
    item["title"] = title
    item["totalScore"] = total_score
    item["reviewsCount"] = reviews_count
    return item


def test_persist_snapshots_creates_from_place_aggregate(session: Session) -> None:
    catalog = _catalog()
    items = [_place_item("ChIJtracked", title="Tracked Cafe", total_score=4.5)]

    summary = persist_snapshots(
        session,
        items=items,
        catalog=catalog,
        snapshot_date=date(2025, 7, 1),
        cadence="weekly",
        week_start="monday",
    )

    assert summary["snapshots_created"] == 1
    snap = session.scalars(select(PlaceSnapshot)).one()
    assert snap.rating == 4.5
    assert snap.user_ratings_total == 1200
    assert snap.provider_name == "Tracked Cafe"  # title -> name (name-change source)
    assert snap.business_status is None  # dropped; dormancy covers closed venues
    assert snap.price_level is None  # dropped; unused in scoring


def test_persist_snapshots_is_idempotent_per_period(session: Session) -> None:
    catalog = _catalog()
    items = [_place_item("ChIJtracked")]
    kwargs = dict(
        catalog=catalog,
        snapshot_date=date(2025, 7, 1),
        cadence="weekly",
        week_start="monday",
    )

    first = persist_snapshots(session, items=items, **kwargs)
    second = persist_snapshots(session, items=items, **kwargs)

    assert first["snapshots_created"] == 1
    assert second["snapshots_created"] == 0
    assert second["snapshots_skipped"] == 1
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 1


def test_persist_snapshots_skips_unmatched_place(session: Session) -> None:
    catalog = _catalog()
    items = [_place_item("ChIJunknown")]

    summary = persist_snapshots(
        session,
        items=items,
        catalog=catalog,
        snapshot_date=date(2025, 7, 1),
        cadence="weekly",
        week_start="monday",
    )

    assert summary["snapshots_created"] == 0
    assert summary["unmatched_place_ids"] == ["ChIJunknown"]


def test_persist_snapshots_flags_name_change(session: Session) -> None:
    catalog = _catalog()
    persist_snapshots(
        session,
        items=[_place_item("ChIJtracked", title="Old Name")],
        catalog=catalog,
        snapshot_date=date(2025, 7, 1),
        cadence="weekly",
        week_start="monday",
    )

    summary = persist_snapshots(
        session,
        items=[_place_item("ChIJtracked", title="New Name")],
        catalog=catalog,
        snapshot_date=date(2025, 7, 8),
        cadence="weekly",
        week_start="monday",
    )

    assert summary["snapshots_created"] == 1
    assert summary["warnings"] == 1
    warning = session.scalars(select(FetchRunWarning)).all()[-1]
    assert warning.warning_code == "venue_name_changed"
    assert warning.details["current_name"] == "New Name"
