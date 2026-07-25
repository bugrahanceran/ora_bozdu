import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.base import (
    PlaceDataProvider,
    PlaceFetchBundle,
    ProviderUnavailableError,
    RawPlacePayload,
)
from app.cadence import period_start_for
from app.catalog import VenueCatalogEntry
from app.models import (
    FetchRun,
    FetchRunWarning,
    PlaceSnapshot,
    Region,
    SnapshotPayload,
    SnapshotReview,
    SnapshotReviewAppearance,
    Venue,
    utcnow,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FetchSummary:
    fetch_run_id: int
    region: str
    snapshot_date: str
    cadence: str
    period_start: str
    status: str
    requested: int
    succeeded: int
    skipped: int
    failed: int
    warnings: tuple[dict[str, Any], ...]
    errors: dict[str, str]


def build_fetch_plan(
    session: Session,
    *,
    region_slug: str,
    active_entries: tuple[VenueCatalogEntry, ...],
    snapshot_date: date,
    cadence: str,
    week_start: str,
    review_sorts: tuple[str, ...],
    provider_name: str,
    max_retries: int,
    seed_payloads_by_place_id: dict[str, tuple[RawPlacePayload, ...]] | None = None,
    anchor_date: date | None = None,
) -> dict[str, Any]:
    """Describe what a fetch run would do without calling the provider."""
    period_start = period_start_for(
        snapshot_date, cadence=cadence, week_start=week_start, anchor_date=anchor_date
    )
    seed_payloads_by_place_id = seed_payloads_by_place_id or {}
    venue_rows = {
        row.provider_place_id: row
        for row in session.execute(
            select(Venue.id, Venue.slug, Venue.provider_place_id).where(
                Venue.provider_place_id.in_(entry.place_id for entry in active_entries)
            )
        )
    }

    venues_plan: list[dict[str, Any]] = []
    for entry in active_entries:
        row = venue_rows.get(entry.place_id)
        existing_snapshot_id = (
            session.scalar(
                select(PlaceSnapshot.id).where(
                    PlaceSnapshot.venue_id == row.id,
                    PlaceSnapshot.cadence == cadence,
                    PlaceSnapshot.period_start == period_start,
                )
            )
            if row is not None
            else None
        )
        if existing_snapshot_id is not None:
            venues_plan.append(
                {
                    "slug": entry.slug,
                    "action": "skip_existing",
                    "http_requests": 0,
                    "seeded_sorts": [],
                }
            )
            continue

        seeded_sorts = tuple(
            payload.review_sort
            for payload in seed_payloads_by_place_id.get(entry.place_id, ())
            if payload.review_sort in review_sorts
        )
        venues_plan.append(
            {
                "slug": entry.slug,
                "action": "new_venue" if row is None else "fetch",
                "http_requests": len(review_sorts) - len(seeded_sorts),
                "seeded_sorts": list(seeded_sorts),
            }
        )

    logical_requests = sum(item["http_requests"] for item in venues_plan)
    attempts_per_request = max_retries + 1
    return {
        "endpoint": "Places API Legacy Place Details",
        "provider": provider_name,
        "region": region_slug,
        "cadence": cadence,
        "period_start": period_start.isoformat(),
        "snapshot_date": snapshot_date.isoformat(),
        "review_sorts": list(review_sorts),
        "requested_venues": len(active_entries),
        "already_captured": sum(
            item["action"] == "skip_existing" for item in venues_plan
        ),
        "to_fetch": sum(item["action"] != "skip_existing" for item in venues_plan),
        "seeded_from_freshness_cache": sum(
            bool(item["seeded_sorts"]) for item in venues_plan
        ),
        "max_retries": max_retries,
        "estimated_http_requests": logical_requests,
        "worst_case_http_requests_with_retries": logical_requests
        * attempts_per_request,
        "venues": venues_plan,
    }


class FetchService:
    def __init__(self, provider: PlaceDataProvider) -> None:
        self._provider = provider

    async def run(
        self,
        session: Session,
        *,
        region_slug: str,
        snapshot_date: date,
        cadence: str,
        week_start: str,
        venue_slugs: tuple[str, ...] | None = None,
        venue_slug: str | None = None,
        seed_payloads_by_place_id: dict[str, tuple[RawPlacePayload, ...]] | None = None,
        anchor_date: date | None = None,
    ) -> FetchSummary:
        region = session.scalar(select(Region).where(Region.slug == region_slug))
        if region is None:
            raise ValueError(f"Unknown region: {region_slug}")
        period_start = period_start_for(
            snapshot_date,
            cadence=cadence,
            week_start=week_start,
            anchor_date=anchor_date,
        )
        venue_query = select(Venue.id, Venue.slug).where(
            Venue.region_id == region.id,
            Venue.is_active.is_(True),
            Venue.is_tracked.is_(True),
        )
        if venue_slugs is not None:
            venue_query = venue_query.where(Venue.slug.in_(venue_slugs))
        if venue_slug is not None:
            venue_query = venue_query.where(Venue.slug == venue_slug)
        venue_rows = list(session.execute(venue_query.order_by(Venue.display_name)))
        venue_ids = [row.id for row in venue_rows]
        if venue_slugs is not None:
            expected_slugs = set(venue_slugs)
            if venue_slug is not None:
                expected_slugs &= {venue_slug}
            missing_slugs = expected_slugs - {row.slug for row in venue_rows}
            if missing_slugs:
                raise ValueError(
                    f"Unknown or inactive catalog venues: {sorted(missing_slugs)}"
                )
        if venue_slug is not None and not venue_ids:
            raise ValueError(
                f"Unknown or inactive venue in region {region_slug!r}: {venue_slug!r}"
            )
        fetch_run = FetchRun(
            region_id=region.id,
            provider=self._provider.provider_name,
            cadence=cadence,
            period_start=period_start,
            requested_count=len(venue_ids),
        )
        session.add(fetch_run)
        session.commit()
        fetch_run_id = fetch_run.id
        errors: dict[str, str] = {}
        warnings: list[dict[str, Any]] = []

        for venue_id in venue_ids:
            venue = session.get(Venue, venue_id)
            if venue is None:
                continue
            existing = session.scalar(
                select(PlaceSnapshot.id).where(
                    PlaceSnapshot.venue_id == venue.id,
                    PlaceSnapshot.cadence == cadence,
                    PlaceSnapshot.period_start == period_start,
                )
            )
            if existing is not None:
                run = session.get(FetchRun, fetch_run_id)
                assert run is not None
                run.skipped_count += 1
                session.commit()
                continue

            try:
                if not venue.provider_place_id:
                    raise ValueError(f"Catalog venue has no place_id: {venue.slug}")

                seed_payloads = (
                    seed_payloads_by_place_id.get(venue.provider_place_id, ())
                    if seed_payloads_by_place_id
                    else ()
                )
                bundle = await self._provider.fetch_place(
                    venue.provider_place_id,
                    existing_payloads=seed_payloads,
                )
                produced_warnings = self._persist_bundle(
                    session,
                    fetch_run_id=fetch_run_id,
                    venue=venue,
                    snapshot_date=snapshot_date,
                    cadence=cadence,
                    period_start=period_start,
                    bundle=bundle,
                )
                warnings.extend(produced_warnings)
                session.commit()
            except IntegrityError:
                session.rollback()
                run = session.get(FetchRun, fetch_run_id)
                assert run is not None
                run.skipped_count += 1
                session.commit()
            except ProviderUnavailableError as exc:
                session.rollback()
                errors[venue.slug] = str(exc)
                run = session.get(FetchRun, fetch_run_id)
                assert run is not None
                run.failed_count += 1
                run.error_summary = errors
                run.finished_at = utcnow()
                run.status = "partial" if run.succeeded_count else "failed"
                session.commit()
                raise
            except Exception as exc:
                session.rollback()
                logger.exception("Venue fetch failed: %s", venue.slug)
                errors[venue.slug] = str(exc)
                run = session.get(FetchRun, fetch_run_id)
                assert run is not None
                run.failed_count += 1
                run.error_summary = errors
                session.commit()

        run = session.get(FetchRun, fetch_run_id)
        assert run is not None
        run.finished_at = utcnow()
        if run.failed_count == 0:
            run.status = "completed"
        elif run.succeeded_count > 0 or run.skipped_count > 0:
            run.status = "partial"
        else:
            run.status = "failed"
        run.error_summary = errors or None
        run.warning_summary = warnings or None
        session.commit()

        return FetchSummary(
            fetch_run_id=fetch_run_id,
            region=region_slug,
            snapshot_date=snapshot_date.isoformat(),
            cadence=cadence,
            period_start=period_start.isoformat(),
            status=run.status,
            requested=run.requested_count,
            succeeded=run.succeeded_count,
            skipped=run.skipped_count,
            failed=run.failed_count,
            warnings=tuple(warnings),
            errors=errors,
        )

    @staticmethod
    def _persist_bundle(
        session: Session,
        *,
        fetch_run_id: int,
        venue: Venue,
        snapshot_date: date,
        cadence: str,
        period_start: date,
        bundle: PlaceFetchBundle,
    ) -> tuple[dict[str, Any], ...]:
        previous = session.scalar(
            select(PlaceSnapshot)
            .where(
                PlaceSnapshot.venue_id == venue.id,
                PlaceSnapshot.period_start < period_start,
            )
            .order_by(PlaceSnapshot.period_start.desc())
            .limit(1)
        )
        state = bundle.state
        snapshot = PlaceSnapshot(
            venue_id=venue.id,
            fetch_run_id=fetch_run_id,
            snapshot_date=snapshot_date,
            cadence=cadence,
            period_start=period_start,
            captured_at=min(payload.fetched_at for payload in bundle.payloads),
            provider_name=state.name,
            rating=state.rating,
            user_ratings_total=state.user_ratings_total,
            price_level=state.price_level,
            business_status=state.business_status,
        )
        session.add(snapshot)
        session.flush()

        payload_models: dict[str, SnapshotPayload] = {}
        for payload in bundle.payloads:
            model = SnapshotPayload(
                snapshot_id=snapshot.id,
                provider="places_api",
                request_variant=payload.request_variant,
                review_sort=payload.review_sort,
                fetched_at=payload.fetched_at,
                raw_payload=payload.body,
                payload_hash=payload.payload_hash,
            )
            session.add(model)
            payload_models[payload.request_variant] = model
        session.flush()

        for review in bundle.reviews:
            review_model = SnapshotReview(
                snapshot_id=snapshot.id,
                source="places_api",
                provider_review_id=review.provider_review_id,
                dedup_key=review.dedup_key,
                author_name=review.author_name,
                author_url=review.author_url,
                published_at=review.published_at,
                rating=review.rating,
                text=review.text,
                language=review.language,
                original_language=review.original_language,
                translated=review.translated,
                raw_review=review.raw_review,
            )
            session.add(review_model)
            session.flush()
            for appearance in review.appearances:
                payload_model = payload_models[appearance.request_variant]
                session.add(
                    SnapshotReviewAppearance(
                        snapshot_review_id=review_model.id,
                        snapshot_payload_id=payload_model.id,
                        review_sort=appearance.review_sort,
                        rank=appearance.rank,
                    )
                )

        run = session.get(FetchRun, fetch_run_id)
        assert run is not None
        run.succeeded_count += 1

        if previous is None:
            return ()

        produced: list[dict[str, Any]] = []
        if previous.provider_name != state.name:
            warning_details = {
                "code": "venue_name_changed",
                "venue_slug": venue.slug,
                "previous_name": previous.provider_name,
                "current_name": state.name,
                "previous_snapshot_date": previous.snapshot_date.isoformat(),
                "current_snapshot_date": snapshot_date.isoformat(),
            }
            logger.warning(
                "venue_name_changed venue=%s previous=%r current=%r",
                venue.slug,
                previous.provider_name,
                state.name,
            )
            session.add(
                FetchRunWarning(
                    fetch_run_id=fetch_run_id,
                    venue_id=venue.id,
                    snapshot_id=snapshot.id,
                    warning_code="venue_name_changed",
                    details=warning_details,
                )
            )
            produced.append(warning_details)

        if previous.business_status != state.business_status:
            warning_details = {
                "code": "venue_status_changed",
                "venue_slug": venue.slug,
                "previous_status": previous.business_status,
                "current_status": state.business_status,
                "previous_snapshot_date": previous.snapshot_date.isoformat(),
                "current_snapshot_date": snapshot_date.isoformat(),
            }
            logger.warning(
                "venue_status_changed venue=%s previous=%r current=%r",
                venue.slug,
                previous.business_status,
                state.business_status,
            )
            session.add(
                FetchRunWarning(
                    fetch_run_id=fetch_run_id,
                    venue_id=venue.id,
                    snapshot_id=snapshot.id,
                    warning_code="venue_status_changed",
                    details=warning_details,
                )
            )
            produced.append(warning_details)

        run.warning_count += len(produced)
        return tuple(produced)
