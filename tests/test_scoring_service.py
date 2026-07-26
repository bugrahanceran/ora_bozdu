from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    FetchRun,
    PlaceSnapshot,
    Region,
    SnapshotReview,
    Venue,
    VenueReview,
)
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine
from app.scoring.service import compute_venue_score

V6 = Path("config/scoring.v6.toml")
AS_OF = date(2026, 7, 25)


def _seed_venue_with_flat_snapshots(session: Session) -> Venue:
    region = Region(slug="eryaman", name="Eryaman")
    session.add(region)
    session.flush()
    venue = Venue(
        region_id=region.id,
        slug="cafe",
        display_name="Cafe",
        provider="places_api",
        provider_place_id="ChIJx",
    )
    session.add(venue)
    fetch_run = FetchRun(
        region_id=region.id,
        provider="places_api",
        cadence="biweekly",
        period_start=AS_OF,
    )
    session.add(fetch_run)
    session.flush()
    for offset in (4, 0):  # flat aggregate rating across two snapshots
        snapshot_date = AS_OF - timedelta(days=offset)
        session.add(
            PlaceSnapshot(
                venue_id=venue.id,
                fetch_run_id=fetch_run.id,
                snapshot_date=snapshot_date,
                cadence="biweekly",
                period_start=snapshot_date,
                captured_at=datetime(2026, 7, 1, tzinfo=UTC),
                provider_name="Cafe",
                rating=4.3,
                user_ratings_total=3000,
            )
        )
    session.commit()
    return venue


def test_corpus_is_preferred_and_drives_the_review_split_trajectory(
    session: Session,
) -> None:
    venue = _seed_venue_with_flat_snapshots(session)
    snapshot_id = session.scalar(
        select(PlaceSnapshot.id).where(PlaceSnapshot.venue_id == venue.id)
    )
    # A thin, positive SnapshotReview set that -- if used -- would NOT flip the
    # score negative; the rich backfill corpus (recent 2-star) must win.
    session.add(
        SnapshotReview(
            snapshot_id=snapshot_id,
            source="places_api",
            dedup_key="snap-1",
            author_name="A",
            published_at=datetime(2026, 7, 20, tzinfo=UTC),
            rating=5,
            text="taze",
            raw_review={},
        )
    )
    for index in range(15):
        session.add(
            VenueReview(
                venue_id=venue.id,
                source="backfill",
                dedup_key=f"old-{index}",
                author_name="x",
                published_at=datetime(2026, 3, 7, tzinfo=UTC),
                rating=5,
                text="lezzetli",
            )
        )
        session.add(
            VenueReview(
                venue_id=venue.id,
                source="backfill",
                dedup_key=f"new-{index}",
                author_name="y",
                published_at=datetime(2026, 7, 10, tzinfo=UTC),
                rating=2,
                text="pahalı",
            )
        )
    session.commit()

    engine = ScoringEngine(load_scoring_config(V6))
    result = compute_venue_score(session, venue_id=venue.id, engine=engine)

    assert result is not None
    trajectory = result.signal_breakdown["rating_trajectory"]
    assert trajectory["details"]["mode"] == "review_split"
    assert result.classification == "bozdu"


def test_falls_back_to_snapshot_reviews_when_no_corpus(session: Session) -> None:
    venue = _seed_venue_with_flat_snapshots(session)

    engine = ScoringEngine(load_scoring_config(V6))
    result = compute_venue_score(session, venue_id=venue.id, engine=engine)

    assert result is not None
    # No backfill corpus -> aggregate-snapshot trajectory (v5 behavior).
    assert result.signal_breakdown["rating_trajectory"]["details"]["mode"] == (
        "aggregate_snapshot"
    )
