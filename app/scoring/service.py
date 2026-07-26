from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    PlaceSnapshot,
    Region,
    ScoreResult,
    SnapshotReview,
    Venue,
    VenueReview,
    utcnow,
)
from app.scoring.engine import ReviewInput, ScoreComputation, ScoringEngine


def _reviews_for_scoring(
    session: Session,
    *,
    venue_id: int,
    snapshot_ids: list[int],
    as_of_date: date,
) -> list[ReviewInput]:
    """Prefer the scraped backfill corpus; fall back to per-snapshot reviews.

    When a venue has a `venue_reviews` corpus it is a far richer, date-consistent
    substrate for the review-based signals (sentiment, review-window trajectory),
    so it wins; otherwise the forward SnapshotReview rows keep v5 behavior. Bounded
    to `as_of_date` so scoring a past snapshot never uses future reviews.
    """
    corpus = list(
        session.scalars(
            select(VenueReview).where(VenueReview.venue_id == venue_id)
        ).all()
    )
    corpus = [review for review in corpus if review.published_at.date() <= as_of_date]
    if corpus:
        return corpus
    return list(
        session.scalars(
            select(SnapshotReview).where(SnapshotReview.snapshot_id.in_(snapshot_ids))
        ).all()
    )


def compute_venue_score(
    session: Session,
    *,
    venue_id: int,
    engine: ScoringEngine,
    as_of_snapshot_id: int | None = None,
) -> ScoreResult | None:
    snapshot_query = select(PlaceSnapshot).where(PlaceSnapshot.venue_id == venue_id)
    if as_of_snapshot_id is not None:
        as_of = session.get(PlaceSnapshot, as_of_snapshot_id)
        if as_of is None or as_of.venue_id != venue_id:
            raise ValueError("Invalid as_of_snapshot_id for venue")
        snapshot_query = snapshot_query.where(
            PlaceSnapshot.snapshot_date <= as_of.snapshot_date
        )
    snapshots = list(
        session.scalars(snapshot_query.order_by(PlaceSnapshot.snapshot_date)).all()
    )
    if not snapshots:
        return None
    as_of = snapshots[-1]
    snapshot_ids = [snapshot.id for snapshot in snapshots]
    reviews = _reviews_for_scoring(
        session,
        venue_id=venue_id,
        snapshot_ids=snapshot_ids,
        as_of_date=as_of.snapshot_date,
    )
    computation = engine.compute(snapshots, reviews)
    result = session.scalar(
        select(ScoreResult).where(
            ScoreResult.venue_id == venue_id,
            ScoreResult.as_of_snapshot_id == as_of.id,
            ScoreResult.score_version == computation.score_version,
        )
    )
    if result is None:
        result = ScoreResult(
            venue_id=venue_id,
            as_of_snapshot_id=as_of.id,
            score_version=computation.score_version,
            change_score=computation.change_score,
            confidence=computation.confidence,
            classification=computation.classification,
            stability_state=computation.stability_state,
            signal_breakdown=computation.signal_breakdown,
            change_story=computation.change_story,
        )
        session.add(result)
    else:
        _apply_computation(result, computation)
        result.computed_at = utcnow()
    session.flush()
    return result


def recompute_region(
    session: Session,
    *,
    region_slug: str,
    engine: ScoringEngine,
) -> int:
    region = session.scalar(select(Region).where(Region.slug == region_slug))
    if region is None:
        raise ValueError(f"Unknown region: {region_slug}")
    venue_ids = session.scalars(
        select(Venue.id).where(Venue.region_id == region.id, Venue.is_active.is_(True))
    ).all()
    computed = 0
    for venue_id in venue_ids:
        if compute_venue_score(session, venue_id=venue_id, engine=engine) is not None:
            computed += 1
    session.commit()
    return computed


def _apply_computation(result: ScoreResult, computation: ScoreComputation) -> None:
    result.change_score = computation.change_score
    result.confidence = computation.confidence
    result.classification = computation.classification
    result.stability_state = computation.stability_state
    result.signal_breakdown = computation.signal_breakdown
    result.change_story = computation.change_story
