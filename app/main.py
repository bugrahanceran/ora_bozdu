from collections import Counter
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.models import PlaceSnapshot, ScoreResult, Venue
from app.scoring.config import load_scoring_config

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
ACTIVE_SCORE_VERSION = load_scoring_config(get_settings().scoring_config_path).version

app = FastAPI(title=get_settings().app_name)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

SessionDependency = Annotated[Session, Depends(get_session)]
SIGNAL_LABELS = {
    "rating_trajectory": "Rating eğilimi",
    "review_velocity": "Review hızı",
    "sentiment_keyword_drift": "Sentiment ve kelime değişimi",
    "stability": "İstikrar",
}
STABILITY_LABELS = {
    "stable_high": "İstikrarlı",
    "stable_low": "Durgun",
    "volatile": "Dalgalı",
    "dormant": "Sessizleşti",
    "insufficient_data": "Veri birikiyor",
}
CLASSIFICATION_LABELS = {
    "costu": "Coştu",
    "bozdu": "Bozdu",
    "dengede": "Dengede",
}


def _search_query(query: str):
    pattern = f"%{query.strip()}%"
    return (
        select(Venue)
        .where(
            Venue.is_active.is_(True),
            or_(
                Venue.display_name.ilike(pattern),
                Venue.slug.ilike(pattern),
            ),
        )
        .order_by(Venue.display_name)
        .limit(20)
    )


def _latest_snapshot(session: Session, venue_id: int) -> PlaceSnapshot | None:
    return session.scalar(
        select(PlaceSnapshot)
        .where(PlaceSnapshot.venue_id == venue_id)
        .order_by(PlaceSnapshot.snapshot_date.desc(), PlaceSnapshot.id.desc())
        .limit(1)
    )


def _latest_score(
    session: Session,
    venue_id: int,
    snapshot_id: int | None,
) -> ScoreResult | None:
    if snapshot_id is None:
        return None
    return session.scalar(
        select(ScoreResult)
        .where(
            ScoreResult.venue_id == venue_id,
            ScoreResult.as_of_snapshot_id == snapshot_id,
            ScoreResult.score_version == ACTIVE_SCORE_VERSION,
        )
        .order_by(ScoreResult.computed_at.desc())
        .limit(1)
    )


def _venue_payload(session: Session, venue: Venue) -> dict[str, Any]:
    snapshot = _latest_snapshot(session, venue.id)
    score = _latest_score(session, venue.id, snapshot.id if snapshot else None)
    signal_items = []
    if score:
        signal_items = [
            {
                "key": key,
                "label": SIGNAL_LABELS[key],
                **value,
            }
            for key, value in score.signal_breakdown.items()
        ]
    return {
        "venue": venue,
        "snapshot": snapshot,
        "score": score,
        "bar_position": (score.change_score + 100) / 2 if score else 50,
        "stability_label": (
            STABILITY_LABELS.get(score.stability_state, score.stability_state)
            if score
            else "Veri bekleniyor"
        ),
        "signals": signal_items,
    }


def _overview_payload(session: Session) -> dict[str, Any]:
    row_number = (
        func.row_number()
        .over(
            partition_by=PlaceSnapshot.venue_id,
            order_by=(PlaceSnapshot.snapshot_date.desc(), PlaceSnapshot.id.desc()),
        )
        .label("row_number")
    )
    latest_snapshot_ids = select(
        PlaceSnapshot.id.label("snapshot_id"), row_number
    ).subquery()
    rows = session.execute(
        select(Venue, PlaceSnapshot, ScoreResult)
        .join(PlaceSnapshot, PlaceSnapshot.venue_id == Venue.id)
        .join(
            latest_snapshot_ids,
            (latest_snapshot_ids.c.snapshot_id == PlaceSnapshot.id)
            & (latest_snapshot_ids.c.row_number == 1),
        )
        .join(
            ScoreResult,
            (ScoreResult.venue_id == Venue.id)
            & (ScoreResult.as_of_snapshot_id == PlaceSnapshot.id)
            & (ScoreResult.score_version == ACTIVE_SCORE_VERSION),
        )
        .where(Venue.is_active.is_(True))
        .order_by(ScoreResult.change_score.desc(), Venue.display_name)
    ).all()
    venues = [
        {
            "venue": venue,
            "snapshot": snapshot,
            "score": score,
            "bar_position": (score.change_score + 100) / 2,
            "classification_label": CLASSIFICATION_LABELS[score.classification],
            "stability_label": STABILITY_LABELS.get(
                score.stability_state, score.stability_state
            ),
        }
        for venue, snapshot, score in rows
    ]
    counts = Counter(item["score"].classification for item in venues)
    return {
        "venues": venues,
        "counts": {
            "total": len(venues),
            "costu": counts["costu"],
            "dengede": counts["dengede"],
            "bozdu": counts["bozdu"],
        },
        "snapshot_date": rows[0][1].snapshot_date if rows else None,
    }


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    session: SessionDependency,
    q: str = Query(default="", max_length=120),
) -> HTMLResponse:
    venues = list(session.scalars(_search_query(q)).all()) if q.strip() else []
    overview = _overview_payload(session)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"query": q, "venues": venues, "overview": overview},
    )


@app.get("/venues/{slug}", response_class=HTMLResponse)
def venue_detail(
    request: Request, slug: str, session: SessionDependency
) -> HTMLResponse:
    venue = session.scalar(select(Venue).where(Venue.slug == slug))
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    return templates.TemplateResponse(
        request=request,
        name="venue.html",
        context=_venue_payload(session, venue),
    )


@app.get("/api/venues")
def search_venues(
    session: SessionDependency,
    q: str = Query(min_length=1, max_length=120),
) -> list[dict[str, Any]]:
    venues = session.scalars(_search_query(q)).all()
    return [
        {
            "slug": venue.slug,
            "name": venue.display_name,
            "has_place_id": venue.provider_place_id is not None,
        }
        for venue in venues
    ]


@app.get("/api/venues/{slug}")
def venue_api(slug: str, session: SessionDependency) -> dict[str, Any]:
    venue = session.scalar(select(Venue).where(Venue.slug == slug))
    if venue is None:
        raise HTTPException(status_code=404, detail="Venue not found")
    data = _venue_payload(session, venue)
    snapshot = data["snapshot"]
    score = data["score"]
    return {
        "venue": {"slug": venue.slug, "name": venue.display_name},
        "snapshot": (
            {
                "date": snapshot.snapshot_date.isoformat(),
                "provider_name": snapshot.provider_name,
                "rating": snapshot.rating,
                "user_ratings_total": snapshot.user_ratings_total,
            }
            if snapshot
            else None
        ),
        "score": (
            {
                "version": score.score_version,
                "change_score": score.change_score,
                "confidence": score.confidence,
                "classification": score.classification,
                "stability_state": score.stability_state,
                "change_story": score.change_story,
                "signals": score.signal_breakdown,
            }
            if score
            else None
        ),
    }


@app.get("/health")
def health(session: SessionDependency) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ok"}
