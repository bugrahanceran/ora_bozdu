from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.models import PlaceSnapshot, SnapshotReview
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine

CONFIG_PATH = Path("config/scoring.v4.toml")


def make_snapshots(
    ratings: list[float],
    *,
    start: date = date(2026, 5, 1),
    spacing_days: int = 4,
    start_review_count: int = 100,
) -> list[PlaceSnapshot]:
    snapshots = []
    for index, rating in enumerate(ratings):
        snapshot_date = start + timedelta(days=index * spacing_days)
        snapshots.append(
            PlaceSnapshot(
                id=index + 1,
                venue_id=1,
                fetch_run_id=1,
                snapshot_date=snapshot_date,
                cadence="daily",
                period_start=snapshot_date,
                captured_at=datetime(2026, 5, 1, tzinfo=UTC)
                + timedelta(days=index * spacing_days),
                provider_name="Fixture Cafe",
                rating=rating,
                user_ratings_total=start_review_count + index * 4,
                price_level=2,
                business_status="OPERATIONAL",
            )
        )
    return snapshots


def make_review(
    key: str,
    published_at: datetime,
    rating: int,
    text: str,
) -> SnapshotReview:
    return SnapshotReview(
        snapshot_id=1,
        source="places_api",
        dedup_key=key,
        author_name=key,
        published_at=published_at,
        rating=rating,
        text=text,
        raw_review={},
    )


def test_scoring_config_has_four_signals_and_sums_to_one() -> None:
    config = load_scoring_config(CONFIG_PATH)

    assert config.version == "v4"
    assert set(config.weights) == {
        "rating_trajectory",
        "review_velocity",
        "sentiment_keyword_drift",
        "stability",
    }
    assert sum(config.weights.values()) == 1.0
    assert config.weights["review_velocity"] == 0.20
    assert config.weights["stability"] == 0.30


def test_high_stability_is_positive_and_gets_state() -> None:
    snapshots = make_snapshots([4.5] * 7)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    assert result.stability_state == "stable_high"
    assert result.signal_breakdown["stability"]["value"] > 0
    assert result.change_score > 0
    assert "istikrarlı" in result.change_story


def test_low_stability_is_not_rewarded() -> None:
    snapshots = make_snapshots([3.5] * 7)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    assert result.stability_state == "stable_low"
    assert result.signal_breakdown["stability"]["value"] <= 0
    assert result.change_score <= 0


def test_early_phase_has_no_forced_stability_proxy() -> None:
    snapshot = make_snapshots([4.5])[0]
    reviews = [
        make_review(
            "one",
            snapshot.captured_at - timedelta(days=5),
            5,
            "Taze, temiz ve hızlı.",
        ),
        make_review(
            "two",
            snapshot.captured_at - timedelta(days=20),
            4,
            "İlgili ekip.",
        ),
    ]

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(
        [snapshot], reviews
    )

    assert result.stability_state == "insufficient_data"
    assert result.confidence <= 0.45


def test_structural_fields_do_not_change_score() -> None:
    baseline = make_snapshots([4.4, 4.3, 4.2])
    changed = make_snapshots([4.4, 4.3, 4.2])
    changed[-1].provider_name = "Completely Different Name"
    changed[-1].business_status = "CLOSED_PERMANENTLY"
    changed[-1].price_level = 4
    engine = ScoringEngine(load_scoring_config(CONFIG_PATH))

    first = engine.compute(baseline, [])
    second = engine.compute(changed, [])

    assert first.change_score == second.change_score
    assert first.confidence == second.confidence
    assert "structural" not in first.signal_breakdown
