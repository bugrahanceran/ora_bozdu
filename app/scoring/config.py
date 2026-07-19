import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

SIGNAL_NAMES = {
    "rating_trajectory",
    "review_velocity",
    "sentiment_keyword_drift",
    "stability",
}


@dataclass(frozen=True, slots=True)
class RatingTrajectoryConfig:
    full_scale_delta_per_30_days: float
    min_snapshots: int


@dataclass(frozen=True, slots=True)
class ReviewVelocityConfig:
    full_scale_acceleration: float
    full_scale_velocity_per_day: float
    min_snapshots_for_acceleration: int
    review_recency_window_days: int


@dataclass(frozen=True, slots=True)
class SentimentConfig:
    recent_window_days: int
    comparison_window_days: int
    full_scale_sentiment_delta: float
    min_reviews: int


@dataclass(frozen=True, slots=True)
class StabilityConfig:
    high_rating_threshold: float
    window_days: int
    min_snapshots: int
    min_coverage_days: int
    max_rating_stddev: float
    stable_high_value: float
    stable_low_value: float
    volatile_value: float


@dataclass(frozen=True, slots=True)
class ConfidenceConfig:
    early_phase_cap: float
    full_history_snapshots: int
    full_history_days: int


@dataclass(frozen=True, slots=True)
class ClassificationConfig:
    costu_threshold: float
    bozdu_threshold: float


@dataclass(frozen=True, slots=True)
class KeywordConfig:
    positive: tuple[str, ...]
    negative: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScoringConfig:
    version: str
    weights: dict[str, float]
    rating_trajectory: RatingTrajectoryConfig
    review_velocity: ReviewVelocityConfig
    sentiment: SentimentConfig
    stability: StabilityConfig
    confidence: ConfidenceConfig
    classification: ClassificationConfig
    keywords: KeywordConfig


def load_scoring_config(path: Path) -> ScoringConfig:
    with path.open("rb") as config_file:
        data = tomllib.load(config_file)
    weights = {name: float(value) for name, value in data["weights"].items()}
    if set(weights) != SIGNAL_NAMES:
        raise ValueError(f"Scoring weights must contain exactly {sorted(SIGNAL_NAMES)}")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError("Scoring weights must sum to 1.0")
    if any(weight <= 0 for weight in weights.values()):
        raise ValueError("Scoring weights must be positive")
    if not data["version"]:
        raise ValueError("Scoring version is required")

    return ScoringConfig(
        version=data["version"],
        weights=weights,
        rating_trajectory=RatingTrajectoryConfig(**data["rating_trajectory"]),
        review_velocity=ReviewVelocityConfig(**data["review_velocity"]),
        sentiment=SentimentConfig(**data["sentiment_keyword_drift"]),
        stability=StabilityConfig(**data["stability"]),
        confidence=ConfidenceConfig(**data["confidence"]),
        classification=ClassificationConfig(**data["classification"]),
        keywords=KeywordConfig(
            positive=tuple(data["keywords"]["positive"]),
            negative=tuple(data["keywords"]["negative"]),
        ),
    )
