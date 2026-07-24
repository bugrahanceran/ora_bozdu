from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from app.models import PlaceSnapshot, SnapshotReview
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine

CONFIG_PATH = Path("config/scoring.v5.toml")


def make_snapshots(
    ratings: list[float],
    *,
    start: date = date(2026, 5, 1),
    spacing_days: int = 4,
    start_review_count: int = 100,
    review_counts: list[int] | None = None,
) -> list[PlaceSnapshot]:
    snapshots = []
    for index, rating in enumerate(ratings):
        snapshot_date = start + timedelta(days=index * spacing_days)
        review_count = (
            review_counts[index]
            if review_counts is not None
            else start_review_count + index * 4
        )
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
                user_ratings_total=review_count,
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

    assert config.version == "v5"
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


def test_keyword_matching_requires_word_boundaries() -> None:
    snapshot = make_snapshots([4.5])[0]
    reviews = [
        make_review(
            "one",
            snapshot.captured_at - timedelta(days=5),
            5,
            "Badem tatlısı vardı, mekan çok temiz ve ilgili bir ekip var.",
        ),
        make_review(
            "two",
            snapshot.captured_at - timedelta(days=10),
            4,
            "Fiyatlar normal, tekrar geliriz.",
        ),
    ]

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(
        [snapshot], reviews
    )

    details = result.signal_breakdown["sentiment_keyword_drift"]["details"]
    assert details["positive_keyword_hits"] == 2
    assert details["negative_keyword_hits"] == 0


def test_growing_rating_count_prevents_dormancy_even_without_reviews() -> None:
    # user_ratings_total grows every snapshot (no reviews at all) -- rating
    # count activity alone must count as "fresh".
    snapshots = make_snapshots([4.5] * 7)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    details = result.signal_breakdown["stability"]["details"]
    assert details["days_since_activity"] == 0
    assert details["dormancy_penalty"] == 0.0
    assert details["state"] == "stable_high"


def test_never_active_venue_still_gets_dormancy_penalty() -> None:
    # Rating count never grows even once (flat from the very first snapshot
    # we have) and there is not a single review. This is total silence, not
    # "no evidence" -- it must not be treated as fresh just because there is
    # no reference activity date to measure from.
    snapshots = make_snapshots([4.5] * 60, spacing_days=7, review_counts=[100] * 60)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    details = result.signal_breakdown["stability"]["details"]
    assert details["days_since_activity"] is not None
    assert details["days_since_activity"] >= 365
    assert details["state"] == "dormant"
    assert result.signal_breakdown["stability"]["value"] < 0


def test_dormancy_penalty_ramps_up_with_inactivity_duration() -> None:
    config = load_scoring_config(CONFIG_PATH).stability

    assert ScoringEngine._dormancy_penalty(config.dormancy_grace_days, config) == 0.0
    penalty_at_120_days = ScoringEngine._dormancy_penalty(120, config)
    penalty_at_180_days = ScoringEngine._dormancy_penalty(180, config)
    penalty_at_full = ScoringEngine._dormancy_penalty(
        config.dormancy_full_penalty_days, config
    )

    assert penalty_at_120_days < 0
    # Longer inactivity pulls the score down further ("4 ay az, 6 ay biraz
    # daha, uzadıkça artar").
    assert penalty_at_180_days < penalty_at_120_days
    assert penalty_at_full == config.dormancy_penalty_value


def test_full_dormancy_overrides_stable_high_and_pulls_score_down() -> None:
    # Rating count grows once (index 0 -> 1) and then flatlines for the rest
    # of a ~1-year span with no reviews -- confirmed, sustained inactivity.
    review_counts = [100, 105] + [105] * 53
    snapshots = make_snapshots([4.5] * 55, spacing_days=7, review_counts=review_counts)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    details = result.signal_breakdown["stability"]["details"]
    assert details["state"] == "dormant"
    assert details["days_since_activity"] >= 365
    # Full dormancy penalty (-1.0) more than offsets stable_high's +0.75.
    assert result.signal_breakdown["stability"]["value"] < 0
    assert "sessizleşti" in result.change_story


def test_dormancy_alone_stays_dengede_for_a_high_rated_venue() -> None:
    # A venue that was actively growing and rated 4.2, then goes fully quiet
    # (no more rating growth, no reviews) for over a year: dormancy pulls the
    # score down gradually, but on its own -- with rating_trajectory neutral
    # since the number itself never dropped -- it must not crash all the way
    # into "bozdu". Weakening, not collapsing.
    active_weeks = 20
    review_counts = [100 + 5 * i for i in range(active_weeks)]
    review_counts += [review_counts[-1]] * (73 - active_weeks)
    snapshots = make_snapshots([4.2] * 73, spacing_days=7, review_counts=review_counts)

    active_result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(
        snapshots[:20], []
    )
    dormant_result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(
        snapshots, []
    )

    assert active_result.classification == "costu"
    assert dormant_result.signal_breakdown["stability"]["details"]["state"] == "dormant"
    assert dormant_result.change_score < active_result.change_score
    assert dormant_result.classification == "dengede"


def test_dormancy_combined_with_a_low_rating_reaches_bozdu() -> None:
    # Same dormancy, but the frozen rating was already mediocre (stable_low,
    # not stable_high): the two negatives compound into a real "bozdu".
    active_weeks = 20
    review_counts = [100 + 5 * i for i in range(active_weeks)]
    review_counts += [review_counts[-1]] * (73 - active_weeks)
    snapshots = make_snapshots([3.5] * 73, spacing_days=7, review_counts=review_counts)

    result = ScoringEngine(load_scoring_config(CONFIG_PATH)).compute(snapshots, [])

    assert result.signal_breakdown["stability"]["details"]["state"] == "dormant"
    assert result.classification == "bozdu"


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
