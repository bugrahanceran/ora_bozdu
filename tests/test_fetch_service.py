from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.base import PlaceFetchBundle, PlaceState, RawPlacePayload
from app.models import (
    FetchRunWarning,
    PlaceSnapshot,
    Region,
    SnapshotPayload,
    Venue,
)
from app.services.fetch_service import FetchService


def make_bundle(name: str) -> PlaceFetchBundle:
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
            formatted_address="Eryaman, Ankara",
            latitude=39.98,
            longitude=32.65,
            rating=4.4,
            user_ratings_total=100,
            price_level=2,
            business_status="OPERATIONAL",
            types=("cafe",),
            website=None,
            google_maps_url=None,
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
