import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.places_legacy import make_review_key
from app.cadence import period_start_for
from app.catalog import VenueCatalog, load_catalog, sync_catalog
from app.config import get_settings
from app.data_collection_config import load_data_collection_config
from app.db import SessionLocal
from app.models import (
    FetchRun,
    FetchRunWarning,
    PlaceSnapshot,
    Region,
    Venue,
    VenueReview,
    utcnow,
)
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine
from app.scoring.service import recompute_region

BACKFILL_LOOKBACK_DAYS = 365
# Newest 50 reviews per venue -- enough signal for sentiment drift + a
# 12-month rating trajectory while keeping the (paid) review count low.
DEFAULT_REVIEWS_LIMIT = 50
# Apify actor that scrapes Google Maps reviews. One run takes every tracked
# place_id at once; Apify queues them internally, so we do not batch calls.
APIFY_ACTOR = "compass/google-maps-reviews-scraper"
# Published Apify pricing (2026-07): pay-per-event from ~$0.30 per 1000 scraped
# reviews. A rough --plan estimate only; the operator's own plan/tier and the
# $5/month free platform credit are authoritative.
APIFY_USD_PER_1000 = 0.30


@dataclass(frozen=True, slots=True)
class ParsedReview:
    provider_review_id: str | None
    author_name: str
    published_at: datetime
    rating: int
    text: str
    language: str | None
    sub_ratings: dict[str, Any] | None


def _parse_published(review: dict[str, Any]) -> datetime | None:
    # Apify gives an ISO 8601 publishedAtDate (e.g. "2021-07-26T13:00:48.000Z").
    # publishAt is a relative string ("3 months ago") and is intentionally
    # ignored -- the backfill signals need an exact date.
    raw = str(review.get("publishedAtDate") or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def parse_apify_review(review: dict[str, Any]) -> ParsedReview | None:
    """One Apify review dict -> ParsedReview, or None to skip.

    Skips reviews without a parseable date or a valid 1-5 star rating -- the
    backfill signals need dated, rated reviews.
    """
    published_at = _parse_published(review)
    if published_at is None:
        return None
    try:
        rating = round(float(review.get("stars")))
    except (TypeError, ValueError):
        return None
    if not 1 <= rating <= 5:
        return None
    review_id = review.get("reviewId")
    author = review.get("name") or review.get("reviewerId")
    # Per-review category stars (Food/Service/Atmosphere); only some reviewers
    # fill these, so Apify sends {} when absent -> store None, not an empty dict.
    detailed = review.get("reviewDetailedRating")
    sub_ratings = detailed if isinstance(detailed, dict) and detailed else None
    return ParsedReview(
        provider_review_id=str(review_id) if review_id else None,
        author_name=str(author or "A Google user"),
        published_at=published_at,
        rating=rating,
        text=str(review.get("text") or review.get("textTranslated") or ""),
        language=review.get("language") or review.get("originalLanguage") or None,
        sub_ratings=sub_ratings,
    )


def _dedup_key(place_id: str, parsed: ParsedReview) -> str:
    # Prefer Apify's stable reviewId; else a content hash.
    if parsed.provider_review_id:
        return hashlib.sha256(
            f"{place_id}\x1f{parsed.provider_review_id}".encode()
        ).hexdigest()
    return make_review_key(
        place_id,
        {
            "author_name": parsed.author_name,
            "time": parsed.published_at.isoformat(),
            "rating": parsed.rating,
            "text": parsed.text,
        },
    )


def _iter_reviews(items: list[Any]):
    # Apify returns a flat list of review dicts; guard against one-level nesting.
    for item in items:
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            yield from (sub for sub in item if isinstance(sub, dict))


def persist_reviews(
    session: Session,
    *,
    items: list[Any],
    catalog: VenueCatalog,
    scraped_at: datetime | None = None,
) -> dict[str, Any]:
    """Persist Apify review items into venue_reviews, joined by placeId.

    Apify emits one dataset item per review, each carrying Google's ChIJ
    placeId, so the join is a direct match to Venue.provider_place_id -- no slug
    bridge needed. Upsert on (venue_id, dedup_key) makes re-imports idempotent.
    """
    scraped_at = scraped_at or utcnow()
    sync_catalog(session, catalog)
    catalog_place_ids = [entry.place_id for entry in catalog.venues]
    venues_by_place_id = {
        row.provider_place_id: row
        for row in session.scalars(
            select(Venue).where(Venue.provider_place_id.in_(catalog_place_ids))
        )
    }
    venue_ids = [venue.id for venue in venues_by_place_id.values()]
    existing = {
        (row.venue_id, row.dedup_key): row
        for row in session.scalars(
            select(VenueReview).where(VenueReview.venue_id.in_(venue_ids))
        )
    }

    added = 0
    updated = 0
    skipped = 0
    unmatched_place_ids: set[str] = set()
    per_venue: dict[str, int] = {}

    for review in _iter_reviews(items):
        place_id = review.get("placeId") or review.get("place_id")
        venue = venues_by_place_id.get(place_id)
        if venue is None:
            if place_id:
                unmatched_place_ids.add(str(place_id))
            continue
        parsed = parse_apify_review(review)
        if parsed is None:
            skipped += 1
            continue
        dedup_key = _dedup_key(venue.provider_place_id, parsed)
        current = existing.get((venue.id, dedup_key))
        if current is None:
            review_row = VenueReview(
                venue_id=venue.id,
                source="backfill",
                provider_review_id=parsed.provider_review_id,
                dedup_key=dedup_key,
                author_name=parsed.author_name,
                published_at=parsed.published_at,
                rating=parsed.rating,
                text=parsed.text,
                language=parsed.language,
                sub_ratings=parsed.sub_ratings,
                scraped_at=scraped_at,
            )
            session.add(review_row)
            existing[(venue.id, dedup_key)] = review_row
            added += 1
        else:
            current.author_name = parsed.author_name
            current.published_at = parsed.published_at
            current.rating = parsed.rating
            current.text = parsed.text
            current.language = parsed.language
            current.sub_ratings = parsed.sub_ratings
            current.scraped_at = scraped_at
            updated += 1
        per_venue[venue.slug] = per_venue.get(venue.slug, 0) + 1

    session.commit()
    return {
        "added": added,
        "updated": updated,
        "skipped": skipped,
        "venues_with_reviews": len(per_venue),
        "unmatched_place_ids": sorted(unmatched_place_ids),
    }


def _group_by_place_id(items: list[Any]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for review in _iter_reviews(items):
        place_id = review.get("placeId") or review.get("place_id")
        if place_id:
            groups.setdefault(str(place_id), []).append(review)
    return groups


def _place_aggregate(place_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pull the venue-level aggregate that Apify attaches to every review item.

    totalScore == Google's aggregate rating, reviewsCount == user_ratings_total,
    title == the venue's current provider name. These are identical across a
    venue's reviews, so the first non-null wins.
    """
    title: str | None = None
    rating: float | None = None
    count: int | None = None
    for item in place_items:
        if title is None and item.get("title"):
            title = str(item["title"])
        if rating is None and item.get("totalScore") is not None:
            try:
                rating = float(item["totalScore"])
            except (TypeError, ValueError):
                pass
        if count is None and item.get("reviewsCount") is not None:
            try:
                count = int(item["reviewsCount"])
            except (TypeError, ValueError):
                pass
    return {"title": title, "rating": rating, "user_ratings_total": count}


def persist_snapshots(
    session: Session,
    *,
    items: list[Any],
    catalog: VenueCatalog,
    snapshot_date: date,
    cadence: str,
    week_start: str,
    anchor_date: date | None = None,
    provider: str = "apify",
    scraped_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a PlaceSnapshot per venue from Apify's place-level aggregate.

    Apify replaces the paid Google Place Details fetch: every review item carries
    the venue's totalScore/reviewsCount/title, which map onto the same snapshot
    fields the scoring time series reads. business_status and price_level are not
    provided (business_status loss is covered by the dormancy signal; price_level
    was never used in scoring), so both stay NULL. Idempotent per
    (venue, cadence, period_start) just like the Google path.
    """
    scraped_at = scraped_at or utcnow()
    sync_catalog(session, catalog)
    region = session.scalar(select(Region).where(Region.slug == catalog.region_slug))
    if region is None:
        raise ValueError(f"Unknown region: {catalog.region_slug}")
    period_start = period_start_for(
        snapshot_date, cadence=cadence, week_start=week_start, anchor_date=anchor_date
    )
    venues_by_place_id = {
        row.provider_place_id: row
        for row in session.scalars(
            select(Venue).where(
                Venue.region_id == region.id,
                Venue.is_active.is_(True),
                Venue.is_tracked.is_(True),
            )
        )
    }
    groups = _group_by_place_id(items)

    fetch_run = FetchRun(
        region_id=region.id,
        provider=provider,
        cadence=cadence,
        period_start=period_start,
        requested_count=len(venues_by_place_id),
    )
    session.add(fetch_run)
    session.commit()

    created = 0
    skipped = 0
    warning_count = 0
    unmatched: set[str] = set()

    for place_id, place_items in groups.items():
        venue = venues_by_place_id.get(place_id)
        if venue is None:
            unmatched.add(place_id)
            continue
        existing = session.scalar(
            select(PlaceSnapshot.id).where(
                PlaceSnapshot.venue_id == venue.id,
                PlaceSnapshot.cadence == cadence,
                PlaceSnapshot.period_start == period_start,
            )
        )
        if existing is not None:
            skipped += 1
            continue
        agg = _place_aggregate(place_items)
        previous = session.scalar(
            select(PlaceSnapshot)
            .where(
                PlaceSnapshot.venue_id == venue.id,
                PlaceSnapshot.period_start < period_start,
            )
            .order_by(PlaceSnapshot.period_start.desc())
            .limit(1)
        )
        name = (
            agg["title"]
            or (previous.provider_name if previous is not None else None)
            or venue.display_name
        )
        snapshot = PlaceSnapshot(
            venue_id=venue.id,
            fetch_run_id=fetch_run.id,
            snapshot_date=snapshot_date,
            cadence=cadence,
            period_start=period_start,
            captured_at=scraped_at,
            provider_name=name,
            rating=agg["rating"],
            user_ratings_total=agg["user_ratings_total"],
            price_level=None,
            business_status=None,
        )
        session.add(snapshot)
        session.flush()
        created += 1

        if previous is not None and previous.provider_name != name:
            details = {
                "code": "venue_name_changed",
                "venue_slug": venue.slug,
                "previous_name": previous.provider_name,
                "current_name": name,
                "previous_snapshot_date": previous.snapshot_date.isoformat(),
                "current_snapshot_date": snapshot_date.isoformat(),
            }
            session.add(
                FetchRunWarning(
                    fetch_run_id=fetch_run.id,
                    venue_id=venue.id,
                    snapshot_id=snapshot.id,
                    warning_code="venue_name_changed",
                    details=details,
                )
            )
            warning_count += 1

    fetch_run.succeeded_count = created
    fetch_run.skipped_count = skipped
    fetch_run.warning_count = warning_count
    fetch_run.finished_at = utcnow()
    fetch_run.status = "completed"
    session.commit()

    return {
        "fetch_run_id": fetch_run.id,
        "period_start": period_start.isoformat(),
        "snapshots_created": created,
        "snapshots_skipped": skipped,
        "warnings": warning_count,
        "unmatched_place_ids": sorted(unmatched),
    }


def _tracked_place_ids(catalog: VenueCatalog) -> list[str]:
    return [
        entry.place_id for entry in catalog.venues if entry.active and entry.tracked
    ]


def _load_catalog(args: argparse.Namespace) -> VenueCatalog:
    catalog_path = args.catalog or get_settings().venue_catalog_path
    return load_catalog(catalog_path)


def _load_collection_config(args: argparse.Namespace):
    path = args.data_collection_config or get_settings().data_collection_config_path
    return load_data_collection_config(path)


def _snapshot_date(args: argparse.Namespace) -> date:
    if args.date is not None:
        return args.date
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def _fetch_plan(
    catalog: VenueCatalog,
    *,
    reviews_limit: int,
    lookback_days: int,
    snapshot_date: date,
    cadence: str,
    week_start: str,
    anchor_date: date | None,
) -> dict[str, Any]:
    place_ids = _tracked_place_ids(catalog)
    max_reviews = len(place_ids) * reviews_limit
    est_cost = round(max_reviews / 1000 * APIFY_USD_PER_1000, 4)
    cutoff_date = (datetime.now(UTC) - timedelta(days=lookback_days)).date()
    period_start = period_start_for(
        snapshot_date, cadence=cadence, week_start=week_start, anchor_date=anchor_date
    )
    return {
        "provider": "apify_google_maps_reviews",
        "actor": APIFY_ACTOR,
        "region": catalog.region_slug,
        "produces": "place_snapshots + venue_reviews + v6 recompute",
        "tracked_venues": len(place_ids),
        "reviews_limit_per_venue": reviews_limit,
        "reviews_start_date": f"{lookback_days} days",
        "cutoff_after": cutoff_date.isoformat(),
        "cadence": cadence,
        "snapshot_date": snapshot_date.isoformat(),
        "period_start": period_start.isoformat(),
        "apify_runs": 1,
        "estimated_max_reviews": max_reviews,
        "estimated_cost_usd_max": est_cost,
        "cost_note": (
            f"Ust sinir: {max_reviews} review; ~${APIFY_USD_PER_1000}/1000 "
            "(pay-per-event, yayinlanan taban fiyat). Apify ucretsiz planinda "
            "aylik $5 platform kredisi bu backfill'i kapsayabilir. Gercek sayi "
            "cutoff/az-review ile daha dusuk olur."
        ),
    }


def _run_fetch(args: argparse.Namespace) -> int:
    settings = get_settings()
    catalog = _load_catalog(args)
    collection_config = _load_collection_config(args)
    if (
        catalog.region_slug != args.region
        or collection_config.region.slug != args.region
    ):
        raise SystemExit("Catalog, data-collection config and --region must match")
    fetch_config = collection_config.fetch
    snapshot_date = _snapshot_date(args)
    if args.plan:
        plan = _fetch_plan(
            catalog,
            reviews_limit=args.reviews_limit,
            lookback_days=args.lookback_days,
            snapshot_date=snapshot_date,
            cadence=fetch_config.cadence,
            week_start=fetch_config.week_start,
            anchor_date=fetch_config.cadence_anchor_date,
        )
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    if settings.apify_api_token is None:
        raise SystemExit("APIFY_TOKEN is required")
    place_ids = _tracked_place_ids(catalog)
    if not place_ids:
        raise SystemExit("No tracked venues to fetch")

    from apify_client import ApifyClient  # lazy: only the real run needs it

    client = ApifyClient(settings.apify_api_token.get_secret_value())
    run_input = {
        "placeIds": place_ids,
        "maxReviews": args.reviews_limit,
        "reviewsSort": "newest",
        "reviewsStartDate": f"{args.lookback_days} days",
        "language": "tr",
        "reviewsOrigin": "all",
        "personalData": True,
    }
    # apify-client 3.x returns a pydantic Run model (not a dict); the dataset id
    # is run.default_dataset_id (snake_case attribute), not a mapping key.
    run = client.actor(APIFY_ACTOR).call(run_input=run_input)
    if run is None or not run.default_dataset_id:
        raise SystemExit("Apify run did not return a dataset")
    dataset_id = run.default_dataset_id
    items = list(client.dataset(dataset_id).iterate_items())

    # Persist the paid raw response before importing so it is never lost.
    raw_path = args.raw_out or Path(f"data/apify-{args.region}.json")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    with SessionLocal() as session:
        review_summary = persist_reviews(session, items=items, catalog=catalog)
        snapshot_summary = persist_snapshots(
            session,
            items=items,
            catalog=catalog,
            snapshot_date=snapshot_date,
            cadence=fetch_config.cadence,
            week_start=fetch_config.week_start,
            anchor_date=fetch_config.cadence_anchor_date,
        )
        recomputed = recompute_region(
            session,
            region_slug=args.region,
            engine=ScoringEngine(load_scoring_config(settings.scoring_config_path)),
        )
    summary = {
        "reviews": review_summary,
        "snapshots": snapshot_summary,
        "recomputed_venues": recomputed,
        "raw_response": str(raw_path),
        "apify_run_id": getattr(run, "id", None),
        "apify_dataset_id": dataset_id,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def _run_import(args: argparse.Namespace) -> int:
    catalog = _load_catalog(args)
    if catalog.region_slug != args.region:
        raise SystemExit("Catalog region does not match --region")
    items = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("Apify JSON must be a list of review objects")
    with SessionLocal() as session:
        summary = persist_reviews(session, items=items, catalog=catalog)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apify data pull: place_snapshots + venue_reviews backfill"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch = subparsers.add_parser(
        "fetch",
        help="Run the Apify actor for tracked venues: snapshots + reviews + rescore",
    )
    fetch.add_argument("--region", default="eryaman")
    fetch.add_argument("--catalog", type=Path)
    fetch.add_argument("--data-collection-config", type=Path)
    fetch.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Snapshot date in YYYY-MM-DD format; defaults to local today",
    )
    fetch.add_argument("--reviews-limit", type=int, default=DEFAULT_REVIEWS_LIMIT)
    fetch.add_argument("--lookback-days", type=int, default=BACKFILL_LOOKBACK_DAYS)
    fetch.add_argument("--raw-out", type=Path)
    fetch.add_argument(
        "--plan",
        action="store_true",
        help="Show venues, cadence/period, reviews_limit and cost without calling",
    )

    importer = subparsers.add_parser(
        "import", help="Import a saved Apify JSON response into venue_reviews"
    )
    importer.add_argument("--input", type=Path, required=True)
    importer.add_argument("--region", default="eryaman")
    importer.add_argument("--catalog", type=Path)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "fetch":
        raise SystemExit(_run_fetch(args))
    if args.command == "import":
        raise SystemExit(_run_import(args))
    raise AssertionError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
