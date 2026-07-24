from datetime import UTC, date, datetime

import httpx
import pytest
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
            score_version="v4",
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
            assert search.json()[0]["slug"] == "fixture-cafe"
            card = await client.get("/venues/fixture-cafe")
            assert card.status_code == 200
            assert "COŞTU" in card.text
            assert "Veri güveni %72" in card.text
            assert "Kanıt gücü %70" in card.text
            assert "İstikrarlı" not in card.text
            assert "Veriler Coştu yönünü gösteriyor." not in card.text
            api = await client.get("/api/venues/fixture-cafe")
            assert api.json()["score"]["change_score"] == 36
    finally:
        app.dependency_overrides.clear()
