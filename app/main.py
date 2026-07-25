import hashlib
from collections import Counter
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode

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
STATIC_DIR = BASE_DIR / "static"
templates = Jinja2Templates(directory=BASE_DIR / "templates")
ACTIVE_SCORING_CONFIG = load_scoring_config(get_settings().scoring_config_path)
ACTIVE_SCORE_VERSION = ACTIVE_SCORING_CONFIG.version
# Query-string cache buster so browsers never serve a stale app.css/app.js
# from an earlier deploy -- content hash changes, URL changes, cache misses.
templates.env.globals["static_version"] = hashlib.sha256(
    b"".join((STATIC_DIR / name).read_bytes() for name in ("app.css", "app.js"))
).hexdigest()[:10]

app = FastAPI(title=get_settings().app_name)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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


def _search_results(session: Session, query: str) -> list[dict[str, Any]]:
    """Search matches enriched with each venue's latest rating/review count.

    Same display_name repeats across chain branches (Google gives every
    branch the same name), so the rating + review count -- which differ per
    branch -- are what let a human tell them apart in the results. Non-tracked
    venues have no snapshot, so their rating/reviews come back None and the UI
    marks them as untracked instead.
    """
    pattern = f"%{query.strip()}%"
    latest = select(
        PlaceSnapshot.venue_id.label("venue_id"),
        PlaceSnapshot.rating.label("rating"),
        PlaceSnapshot.user_ratings_total.label("user_ratings_total"),
        func.row_number()
        .over(
            partition_by=PlaceSnapshot.venue_id,
            order_by=(
                PlaceSnapshot.snapshot_date.desc(),
                PlaceSnapshot.id.desc(),
            ),
        )
        .label("rn"),
    ).subquery()
    rows = session.execute(
        select(
            Venue.slug,
            Venue.display_name,
            Venue.is_tracked,
            latest.c.rating,
            latest.c.user_ratings_total,
        )
        .outerjoin(latest, (latest.c.venue_id == Venue.id) & (latest.c.rn == 1))
        .where(
            Venue.is_active.is_(True),
            or_(
                Venue.display_name.ilike(pattern),
                Venue.slug.ilike(pattern),
            ),
        )
        .order_by(Venue.display_name)
        .limit(20)
    ).all()
    return [
        {
            "slug": row.slug,
            "name": row.display_name,
            "is_tracked": row.is_tracked,
            "rating": row.rating,
            "user_ratings_total": row.user_ratings_total,
        }
        for row in rows
    ]


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


def _maps_url(venue: Venue) -> str | None:
    # No stored coordinates (dropped in 0003); place_id search is precise anyway.
    if not venue.provider_place_id:
        return None
    params = {
        "api": "1",
        "query": venue.display_name,
        "query_place_id": venue.provider_place_id,
    }
    return f"https://www.google.com/maps/search/?{urlencode(params)}"


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
        "maps_url": _maps_url(venue),
        "snapshot": snapshot,
        "score": score,
        "bar_position": (score.change_score + 100) / 2 if score else 50,
        "stability_label": (
            STABILITY_LABELS.get(score.stability_state, score.stability_state)
            if score
            else "Veri bekleniyor"
        ),
        "signals": signal_items,
        "confidence_config": ACTIVE_SCORING_CONFIG.confidence,
        "stability_config": ACTIVE_SCORING_CONFIG.stability,
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
    venues = _search_results(session, q) if q.strip() else []
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
    return _search_results(session, q)


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
