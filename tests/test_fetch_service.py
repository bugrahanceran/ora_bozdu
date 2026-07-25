from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.base import PlaceFetchBundle, PlaceState, RawPlacePayload
from app.catalog import VenueCatalogEntry
from app.models import (
    FetchRunWarning,
    PlaceSnapshot,
    Region,
    SnapshotPayload,
    Venue,
)
from app.services.fetch_service import FetchService, build_fetch_plan


def make_bundle(name: str, *, business_status: str = "OPERATIONAL") -> PlaceFetchBundle:
    fetched_at = datetime(2026, 7, 18, 8, tzinfo=UTC)
    payloads = tuple(
        RawPlacePayload(
            request_variant=f"details_{review_sort}",
            review_sort=review_sort,
            fetched_at=fetched_at,
            body={"status": "OK", "result": {"name": name, "reviews": []}},
            payload_hash=review_sort * 4,
        )
        for review_sort in ("most_relevant", "newest")
    )
    return PlaceFetchBundle(
        state=PlaceState(
            place_id="place-1",
            name=name,
            rating=4.4,
            user_ratings_total=100,
            price_level=2,
            business_status=business_status,
        ),
        payloads=payloads,
        reviews=(),
    )


class FakeProvider:
    provider_name = "places_api"

    def __init__(self, bundle: PlaceFetchBundle) -> None:
        self.bundle = bundle
        self.fetch_count = 0
        self.error: Exception | None = None

    async def fetch_place(
        self,
        place_id: str,
        *,
        existing_payloads: tuple[RawPlacePayload, ...] = (),
    ) -> PlaceFetchBundle:
        self.fetch_count += 1
        if self.error:
            raise self.error
        return self.bundle

    async def aclose(self) -> None:
        return None


def seed_venue(session: Session) -> Venue:
    region = Region(slug="eryaman", name="Eryaman")
    session.add(region)
    session.flush()
    venue = Venue(
        region_id=region.id,
        slug="fixture-cafe",
        display_name="Fixture Cafe",
        provider="places_api",
        provider_place_id="place-1",
    )
    session.add(venue)
    session.commit()
    return venue


def seed_second_venue(session: Session) -> Venue:
    region = session.scalar(select(Region).where(Region.slug == "eryaman"))
    assert region is not None
    venue = Venue(
        region_id=region.id,
        slug="other-cafe",
        display_name="Other Cafe",
        provider="places_api",
        provider_place_id="place-2",
    )
    session.add(venue)
    session.commit()
    return venue


def seed_untracked_venue(session: Session) -> Venue:
    region = session.scalar(select(Region).where(Region.slug == "eryaman"))
    assert region is not None
    venue = Venue(
        region_id=region.id,
        slug="untracked-cafe",
        display_name="Untracked Cafe",
        provider="places_api",
        provider_place_id="place-3",
        is_tracked=False,
    )
    session.add(venue)
    session.commit()
    return venue


@pytest.mark.asyncio
async def test_weekly_idempotency_and_name_change_warning(session: Session) -> None:
    seed_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    service = FetchService(provider)
    first_day = date(2026, 7, 18)

    first = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day,
        cadence="weekly",
        week_start="monday",
    )
    duplicate = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day + timedelta(days=1),
        cadence="weekly",
        week_start="monday",
    )
    provider.bundle = make_bundle("Fixture Cafe Yeni")
    second = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day + timedelta(days=2),
        cadence="weekly",
        week_start="monday",
    )

    assert first.succeeded == 1
    assert duplicate.skipped == 1
    assert second.succeeded == 1
    assert second.warnings[0]["code"] == "venue_name_changed"
    assert provider.fetch_count == 2
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 2
    assert session.scalar(select(func.count(SnapshotPayload.id))) == 4
    assert session.scalar(select(func.count(FetchRunWarning.id))) == 1


@pytest.mark.asyncio
async def test_business_status_change_produces_warning(session: Session) -> None:
    seed_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    service = FetchService(provider)
    first_day = date(2026, 7, 18)

    await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day,
        cadence="weekly",
        week_start="monday",
    )
    provider.bundle = make_bundle("Fixture Cafe", business_status="CLOSED_TEMPORARILY")
    second = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day + timedelta(days=7),
        cadence="weekly",
        week_start="monday",
    )

    assert second.succeeded == 1
    assert len(second.warnings) == 1
    assert second.warnings[0]["code"] == "venue_status_changed"
    assert second.warnings[0]["previous_status"] == "OPERATIONAL"
    assert second.warnings[0]["current_status"] == "CLOSED_TEMPORARILY"
    assert session.scalar(select(func.count(FetchRunWarning.id))) == 1


@pytest.mark.asyncio
async def test_simultaneous_name_and_status_change_produce_two_warnings(
    session: Session,
) -> None:
    seed_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    service = FetchService(provider)
    first_day = date(2026, 7, 18)

    await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day,
        cadence="weekly",
        week_start="monday",
    )
    provider.bundle = make_bundle(
        "Fixture Cafe Yeni", business_status="CLOSED_PERMANENTLY"
    )
    second = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=first_day + timedelta(days=7),
        cadence="weekly",
        week_start="monday",
    )

    assert {warning["code"] for warning in second.warnings} == {
        "venue_name_changed",
        "venue_status_changed",
    }
    assert session.scalar(select(func.count(FetchRunWarning.id))) == 2


@pytest.mark.asyncio
async def test_failed_fetch_does_not_create_partial_snapshot(session: Session) -> None:
    seed_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    provider.error = RuntimeError("newest request failed")

    summary = await FetchService(provider).run(
        session,
        region_slug="eryaman",
        snapshot_date=date(2026, 7, 18),
        cadence="weekly",
        week_start="monday",
    )

    assert summary.failed == 1
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 0
    assert session.scalar(select(func.count(SnapshotPayload.id))) == 0


@pytest.mark.asyncio
async def test_fetch_can_be_limited_to_one_venue(session: Session) -> None:
    seed_venue(session)
    seed_second_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))

    summary = await FetchService(provider).run(
        session,
        region_slug="eryaman",
        snapshot_date=date(2026, 7, 18),
        cadence="weekly",
        week_start="monday",
        venue_slug="fixture-cafe",
    )

    assert summary.requested == 1
    assert summary.succeeded == 1
    assert provider.fetch_count == 1
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 1


@pytest.mark.asyncio
async def test_fetch_skips_untracked_venues(session: Session) -> None:
    seed_venue(session)
    seed_untracked_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))

    summary = await FetchService(provider).run(
        session,
        region_slug="eryaman",
        snapshot_date=date(2026, 7, 18),
        cadence="weekly",
        week_start="monday",
    )

    assert summary.requested == 1
    assert summary.succeeded == 1
    assert provider.fetch_count == 1
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 1


@pytest.mark.asyncio
async def test_build_fetch_plan_reports_skip_seed_and_new_venue(
    session: Session,
) -> None:
    seed_venue(session)
    seed_second_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    period_day = date(2026, 7, 18)

    await FetchService(provider).run(
        session,
        region_slug="eryaman",
        snapshot_date=period_day,
        cadence="weekly",
        week_start="monday",
        venue_slug="fixture-cafe",
    )

    catalog_entries = (
        VenueCatalogEntry(
            slug="fixture-cafe",
            display_name="Fixture Cafe",
            place_id="place-1",
            category="cafe",
            brand_key="fixture-cafe",
        ),
        VenueCatalogEntry(
            slug="other-cafe",
            display_name="Other Cafe",
            place_id="place-2",
            category="cafe",
            brand_key="other-cafe",
        ),
        VenueCatalogEntry(
            slug="not-yet-synced",
            display_name="Not Yet Synced",
            place_id="place-3",
            category="cafe",
            brand_key="not-yet-synced",
        ),
    )
    seed_payloads = {
        "place-2": (
            RawPlacePayload(
                request_variant="details_newest",
                review_sort="newest",
                fetched_at=datetime(2026, 7, 18, tzinfo=UTC),
                body={"status": "OK", "result": {"reviews": []}},
                payload_hash="hash",
            ),
        )
    }

    plan = build_fetch_plan(
        session,
        region_slug="eryaman",
        active_entries=catalog_entries,
        snapshot_date=period_day,
        cadence="weekly",
        week_start="monday",
        review_sorts=("newest", "most_relevant"),
        provider_name="places_api",
        max_retries=2,
        seed_payloads_by_place_id=seed_payloads,
    )

    by_slug = {item["slug"]: item for item in plan["venues"]}
    assert by_slug["fixture-cafe"]["action"] == "skip_existing"
    assert by_slug["fixture-cafe"]["http_requests"] == 0
    assert by_slug["other-cafe"]["action"] == "fetch"
    assert by_slug["other-cafe"]["http_requests"] == 1
    assert by_slug["other-cafe"]["seeded_sorts"] == ["newest"]
    assert by_slug["not-yet-synced"]["action"] == "new_venue"
    assert by_slug["not-yet-synced"]["http_requests"] == 2
    assert plan["estimated_http_requests"] == 3
    assert plan["already_captured"] == 1
    assert plan["to_fetch"] == 2
    assert plan["seeded_from_freshness_cache"] == 1
    # With max_retries=2, each logical request can take up to 3 HTTP
    # attempts; the worst case must be shown, not just the no-retry count.
    assert plan["max_retries"] == 2
    assert plan["worst_case_http_requests_with_retries"] == 9
    # build_fetch_plan never calls the provider.
    assert provider.fetch_count == 1


@pytest.mark.asyncio
async def test_daily_cadence_allows_next_day_snapshot(session: Session) -> None:
    seed_venue(session)
    provider = FakeProvider(make_bundle("Fixture Cafe"))
    service = FetchService(provider)

    await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=date(2026, 7, 18),
        cadence="daily",
        week_start="monday",
    )
    second = await service.run(
        session,
        region_slug="eryaman",
        snapshot_date=date(2026, 7, 19),
        cadence="daily",
        week_start="monday",
    )

    assert second.succeeded == 1
    assert provider.fetch_count == 2
    assert session.scalar(select(func.count(PlaceSnapshot.id))) == 2
