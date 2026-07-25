from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.main import app
from app.models import FetchRun, PlaceSnapshot, Region, ScoreResult, Venue


def seed_card(session: Session) -> None:
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
    session.flush()
    fetch_run = FetchRun(
        region_id=region.id,
        provider="places_api",
        cadence="weekly",
        period_start=date(2026, 7, 13),
    )
    session.add(fetch_run)
    session.flush()
    snapshot = PlaceSnapshot(
        venue_id=venue.id,
        fetch_run_id=fetch_run.id,
        snapshot_date=date(2026, 7, 18),
        cadence="weekly",
        period_start=date(2026, 7, 13),
        captured_at=datetime(2026, 7, 18, tzinfo=UTC),
        provider_name="Fixture Cafe",
        rating=4.5,
        user_ratings_total=420,
    )
    session.add(snapshot)
    session.flush()
    session.add(
        ScoreResult(
            venue_id=venue.id,
            as_of_snapshot_id=snapshot.id,
            score_version="v5",
            change_score=36,
            confidence=0.72,
            classification="costu",
            stability_state="stable_high",
            signal_breakdown={
                "rating_trajectory": {
                    "available": True,
                    "value": 0.3,
                    "reliability": 0.7,
                    "configured_weight": 0.3,
                    "summary": "Rating eğilimi yükseliyor.",
                    "details": {},
                },
                "review_velocity": {
                    "available": True,
                    "value": 0.2,
                    "reliability": 0.6,
                    "configured_weight": 0.2,
                    "summary": "Review hızı artıyor.",
                    "details": {},
                },
                "sentiment_keyword_drift": {
                    "available": True,
                    "value": 0.1,
                    "reliability": 0.5,
                    "configured_weight": 0.2,
                    "summary": "Yorum dili olumlu.",
                    "details": {},
                },
                "stability": {
                    "available": True,
                    "value": 0.75,
                    "reliability": 0.8,
                    "configured_weight": 0.3,
                    "summary": "Yüksek seviyesini koruyor.",
                    "details": {"state": "stable_high"},
                },
            },
            change_story="Veriler Coştu yönünü gösteriyor.",
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_search_and_card_render(session: Session) -> None:
    seed_card(session)

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            assert (await client.get("/health")).json() == {"status": "ok"}
            home = await client.get("/")
            assert home.status_code == 200
            assert "Eryaman skor panosu" in home.text
            assert "Fixture Cafe" in home.text
            assert "+36.0" in home.text
            search = await client.get("/api/venues", params={"q": "Fixture"})
            assert search.status_code == 200
            hit = search.json()[0]
            assert hit["slug"] == "fixture-cafe"
            # Same-named chain branches are told apart by rating + review count.
            assert hit["rating"] == 4.5
            assert hit["user_ratings_total"] == 420
            assert hit["is_tracked"] is True
            card = await client.get("/venues/fixture-cafe")
            assert card.status_code == 200
            assert "COŞTU" in card.text
            assert "Veri güveni %72" in card.text
            assert "Kanıt gücü %70" in card.text
            assert "İstikrarlı" not in card.text
            assert "Veriler Coştu yönünü gösteriyor." not in card.text
            assert "Haritada gör" in card.text
            assert "query_place_id=place-1" in card.text
            assert "Veri güveni nasıl hesaplanıyor" in card.text
            assert "istikrar sinyali henüz hesaplanamıyor" not in card.text
            api = await client.get("/api/venues/fixture-cafe")
            assert api.json()["score"]["change_score"] == 36
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_search_disambiguates_same_name_branches(session: Session) -> None:
    # Two chain branches share the exact same display_name (as Google returns
    # them). One is tracked with a snapshot, one is untracked with none.
    seed_card(session)  # "Fixture Cafe", tracked, rating 4.5 / 420 reviews
    region = session.scalar(select(Region).where(Region.slug == "eryaman"))
    assert region is not None
    untracked = Venue(
        region_id=region.id,
        slug="fixture-cafe-branch-2",
        display_name="Fixture Cafe",
        provider="places_api",
        provider_place_id="place-2",
        is_tracked=False,
    )
    session.add(untracked)
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            results = (await client.get("/api/venues", params={"q": "Fixture"})).json()
            by_slug = {row["slug"]: row for row in results}
            assert by_slug["fixture-cafe"]["rating"] == 4.5
            assert by_slug["fixture-cafe"]["user_ratings_total"] == 420
            assert by_slug["fixture-cafe"]["is_tracked"] is True
            # The untracked branch has no snapshot -> no rating, flagged so the
            # UI can render "takip edilmiyor" instead of an identical bare name.
            assert by_slug["fixture-cafe-branch-2"]["rating"] is None
            assert by_slug["fixture-cafe-branch-2"]["is_tracked"] is False
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_venue_card_hides_map_link_without_place_id(session: Session) -> None:
    region = Region(slug="eryaman", name="Eryaman")
    session.add(region)
    session.flush()
    venue = Venue(
        region_id=region.id,
        slug="no-place-id-cafe",
        display_name="No Place Id Cafe",
        provider="places_api",
        provider_place_id=None,
    )
    session.add(venue)
    session.commit()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            card = await client.get("/venues/no-place-id-cafe")
            assert card.status_code == 200
            assert "Haritada gör" not in card.text
    finally:
        app.dependency_overrides.clear()


def seed_insufficient_data_card(session: Session) -> None:
    region = Region(slug="eryaman", name="Eryaman")
    session.add(region)
    session.flush()
    venue = Venue(
        region_id=region.id,
        slug="early-phase-cafe",
        display_name="Early Phase Cafe",
        provider="places_api",
        provider_place_id="place-2",
    )
    session.add(venue)
    session.flush()
    fetch_run = FetchRun(
        region_id=region.id,
        provider="places_api",
        cadence="weekly",
        period_start=date(2026, 7, 13),
    )
    session.add(fetch_run)
    session.flush()
    snapshot = PlaceSnapshot(
        venue_id=venue.id,
        fetch_run_id=fetch_run.id,
        snapshot_date=date(2026, 7, 18),
        cadence="weekly",
        period_start=date(2026, 7, 13),
        captured_at=datetime(2026, 7, 18, tzinfo=UTC),
        provider_name="Early Phase Cafe",
        rating=4.2,
        user_ratings_total=50,
    )
    session.add(snapshot)
    session.flush()
    session.add(
        ScoreResult(
            venue_id=venue.id,
            as_of_snapshot_id=snapshot.id,
            score_version="v5",
            change_score=5,
            confidence=0.32,
            classification="dengede",
            stability_state="insufficient_data",
            signal_breakdown={
                "rating_trajectory": {
                    "available": False,
                    "value": 0.0,
                    "reliability": 0.0,
                    "configured_weight": 0.3,
                    "summary": "Rating geçmişi yetersiz.",
                    "details": {},
                },
                "review_velocity": {
                    "available": True,
                    "value": 0.1,
                    "reliability": 0.25,
                    "configured_weight": 0.2,
                    "summary": "Yakın tarihli review'lardan düşük güvenli hız tahmini.",
                    "details": {},
                },
                "sentiment_keyword_drift": {
                    "available": True,
                    "value": 0.2,
                    "reliability": 0.4,
                    "configured_weight": 0.2,
                    "summary": "Review sentiment görünümü yatay.",
                    "details": {},
                },
                "stability": {
                    "available": False,
                    "value": 0.0,
                    "reliability": 0.0,
                    "configured_weight": 0.3,
                    "summary": "İstikrar için periyodik snapshot birikiyor.",
                    "details": {"state": "insufficient_data"},
                },
            },
            change_story="Değişim skoru şimdilik dengede (+5.0).",
        )
    )
    session.commit()


@pytest.mark.asyncio
async def test_venue_card_shows_early_phase_cap_note(session: Session) -> None:
    seed_insufficient_data_card(session)

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            card = await client.get("/venues/early-phase-cafe")
            assert card.status_code == 200
            assert "Veri güveni %32" in card.text
            assert "istikrar sinyali henüz hesaplanamıyor" in card.text
            assert "en fazla %45" in card.text
            assert "Henüz veri yok" in card.text
    finally:
        app.dependency_overrides.clear()
