import re
import statistics
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from typing import Any, Protocol

from app.models import PlaceSnapshot
from app.scoring.config import RatingTrajectoryConfig, ScoringConfig, StabilityConfig


class ReviewInput(Protocol):
    """The review fields scoring needs, shared by SnapshotReview and VenueReview.

    Lets the engine consume either the forward per-snapshot reviews or the
    scraped backfill corpus without caring which ORM model produced them.
    """

    dedup_key: str
    published_at: datetime
    rating: int
    text: str


def _clip(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _compile_keyword_patterns(keywords: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    return tuple(
        re.compile(rf"\b{re.escape(keyword.casefold())}\b") for keyword in keywords
    )


@dataclass(frozen=True, slots=True)
class SignalResult:
    available: bool
    value: float
    reliability: float
    summary: str
    details: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ScoreComputation:
    score_version: str
    change_score: float
    confidence: float
    classification: str
    stability_state: str
    signal_breakdown: dict[str, Any]
    change_story: str


class ScoringEngine:
    def __init__(self, config: ScoringConfig) -> None:
        self.config = config
        self._positive_patterns = _compile_keyword_patterns(config.keywords.positive)
        self._negative_patterns = _compile_keyword_patterns(config.keywords.negative)

    def compute(
        self,
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
    ) -> ScoreComputation:
        if not snapshots:
            raise ValueError("At least one snapshot is required")
        ordered = sorted(snapshots, key=lambda snapshot: snapshot.snapshot_date)
        unique_reviews = list({review.dedup_key: review for review in reviews}.values())
        signals = {
            "rating_trajectory": self._rating_trajectory(ordered, unique_reviews),
            "review_velocity": self._review_velocity(ordered, unique_reviews),
            "sentiment_keyword_drift": self._sentiment_drift(
                ordered[-1].snapshot_date,
                unique_reviews,
            ),
            "stability": self._stability(ordered, unique_reviews),
        }
        available_weight = sum(
            self.config.weights[name]
            for name, result in signals.items()
            if result.available
        )
        if available_weight == 0:
            directional_score = 0.0
            confidence = 0.0
        else:
            normalized_weights = {
                name: self.config.weights[name] / available_weight
                for name, result in signals.items()
                if result.available
            }
            evidence = sum(
                normalized_weights[name] * signals[name].reliability
                for name in normalized_weights
            )
            weighted_direction = sum(
                normalized_weights[name]
                * signals[name].value
                * signals[name].reliability
                for name in normalized_weights
            )
            directional_score = weighted_direction / evidence if evidence else 0.0
            confidence = _clip(evidence, 0.0, 1.0)
            if signals["stability"].details["state"] == "insufficient_data":
                confidence = min(confidence, self.config.confidence.early_phase_cap)

        change_score = round(_clip(directional_score * confidence) * 100, 1)
        confidence = round(confidence, 3)
        classification = self._classification(change_score)
        stability_state = str(signals["stability"].details["state"])
        breakdown = {
            name: {
                "available": result.available,
                "value": round(result.value, 4),
                "reliability": round(result.reliability, 4),
                "configured_weight": self.config.weights[name],
                "summary": result.summary,
                "details": result.details,
            }
            for name, result in signals.items()
        }
        story = self._change_story(
            classification,
            change_score,
            confidence,
            signals,
        )
        return ScoreComputation(
            score_version=self.config.version,
            change_score=change_score,
            confidence=confidence,
            classification=classification,
            stability_state=stability_state,
            signal_breakdown=breakdown,
            change_story=story,
        )

    def _rating_trajectory(
        self,
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
    ) -> SignalResult:
        config = self.config.rating_trajectory
        if config.review_split_enabled:
            split = self._rating_trajectory_from_reviews(reviews, config=config)
            if split is not None:
                return split
        rated = [snapshot for snapshot in snapshots if snapshot.rating is not None]
        if len(rated) < config.min_snapshots:
            return SignalResult(False, 0.0, 0.0, "Rating geçmişi yetersiz.", {})
        coverage_days = (rated[-1].snapshot_date - rated[0].snapshot_date).days
        if coverage_days <= 0:
            return SignalResult(False, 0.0, 0.0, "Rating geçmişi yetersiz.", {})
        rating_delta = float(rated[-1].rating) - float(rated[0].rating)
        delta_per_30_days = rating_delta * 30 / coverage_days
        value = _clip(delta_per_30_days / config.full_scale_delta_per_30_days)
        reliability = min(
            1.0, len(rated) / self.config.confidence.full_history_snapshots
        )
        reliability *= min(
            1.0, coverage_days / self.config.confidence.full_history_days
        )
        direction = (
            "yükseliyor" if value > 0.05 else "düşüyor" if value < -0.05 else "yatay"
        )
        return SignalResult(
            True,
            value,
            reliability,
            f"Rating eğilimi {direction}.",
            {
                "mode": "aggregate_snapshot",
                "first_rating": rated[0].rating,
                "latest_rating": rated[-1].rating,
                "delta_per_30_days": round(delta_per_30_days, 4),
                "coverage_days": coverage_days,
                "snapshot_count": len(rated),
            },
        )

    def _rating_trajectory_from_reviews(
        self,
        reviews: list[ReviewInput],
        *,
        config: RatingTrajectoryConfig,
    ) -> SignalResult | None:
        """Count-split trajectory: newest half of the corpus vs the older half.

        The corpus is ordered by date and split into two equal halves *by count*
        (not calendar), so the recent-vs-older comparison always works regardless
        of how much wall-clock time the reviews span. A busy venue's newest 50
        cover weeks and a quiet venue's cover years, yet both still yield a trend
        the inertial aggregate rating hides. Returns None (so the aggregate
        fallback runs) when the corpus is too thin to split.
        """
        rated = sorted(
            (review for review in reviews if review.rating is not None),
            key=lambda review: review.published_at,
        )
        if len(rated) < 2 * config.review_min_per_split:
            return None
        mid = len(rated) // 2
        older = [review.rating for review in rated[:mid]]
        recent = [review.rating for review in rated[mid:]]
        older_mean = statistics.fmean(older)
        recent_mean = statistics.fmean(recent)
        delta = recent_mean - older_mean
        value = _clip(delta / config.trajectory_full_scale_delta)
        reliability = min(1.0, len(rated) / config.review_full_reliability_count)
        span_days = (rated[-1].published_at.date() - rated[0].published_at.date()).days
        direction = (
            "yükseliyor" if value > 0.05 else "düşüyor" if value < -0.05 else "yatay"
        )
        return SignalResult(
            True,
            value,
            reliability,
            f"Rating eğilimi {direction} (yorumlardan).",
            {
                "mode": "review_split",
                "recent_mean_star": round(recent_mean, 4),
                "older_mean_star": round(older_mean, 4),
                "delta": round(delta, 4),
                "recent_review_count": len(recent),
                "older_review_count": len(older),
                "corpus_span_days": span_days,
            },
        )

    def _review_velocity(
        self,
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
    ) -> SignalResult:
        config = self.config.review_velocity
        counted = [
            snapshot
            for snapshot in snapshots
            if snapshot.user_ratings_total is not None
        ]
        intervals: list[float] = []
        for previous, current in pairwise(counted):
            days = (current.snapshot_date - previous.snapshot_date).days
            if days > 0:
                delta = int(current.user_ratings_total) - int(
                    previous.user_ratings_total
                )
                intervals.append(delta / days)

        if (
            len(counted) >= config.min_snapshots_for_acceleration
            and len(intervals) >= 2
        ):
            previous_velocity = statistics.fmean(intervals[:-1])
            current_velocity = intervals[-1]
            acceleration = current_velocity - previous_velocity
            value = _clip(acceleration / config.full_scale_acceleration)
            reliability = min(
                1.0,
                len(counted) / self.config.confidence.full_history_snapshots,
            )
            return SignalResult(
                True,
                value,
                reliability,
                "Review hızı ivmesi hesaplandı.",
                {
                    "current_velocity_per_day": round(current_velocity, 4),
                    "previous_velocity_per_day": round(previous_velocity, 4),
                    "acceleration": round(acceleration, 4),
                    "snapshot_count": len(counted),
                    "mode": "snapshot_acceleration",
                },
            )

        if len(intervals) == 1:
            velocity = intervals[0]
            value = _clip(velocity / config.full_scale_velocity_per_day)
            coverage_days = (counted[-1].snapshot_date - counted[0].snapshot_date).days
            reliability = min(0.5, coverage_days / 30)
            return SignalResult(
                True,
                value,
                reliability,
                "Review artış hızı için ilk ölçüm oluştu.",
                {
                    "velocity_per_day": round(velocity, 4),
                    "coverage_days": coverage_days,
                    "mode": "snapshot_velocity",
                },
            )

        as_of = snapshots[-1].snapshot_date
        recent_reviews = [
            review
            for review in reviews
            if 0
            <= (as_of - review.published_at.date()).days
            <= config.review_recency_window_days
        ]
        if not recent_reviews:
            return SignalResult(False, 0.0, 0.0, "Review hızı için veri yetersiz.", {})
        proxy_velocity = len(recent_reviews) / config.review_recency_window_days
        value = _clip(proxy_velocity / config.full_scale_velocity_per_day)
        reliability = min(0.25, len(recent_reviews) / 20)
        return SignalResult(
            True,
            value,
            reliability,
            "Yakın tarihli review'lardan düşük güvenli hız tahmini üretildi.",
            {
                "recent_review_count": len(recent_reviews),
                "window_days": config.review_recency_window_days,
                "mode": "review_date_proxy",
            },
        )

    def _sentiment_drift(
        self,
        as_of: date,
        reviews: list[ReviewInput],
    ) -> SignalResult:
        config = self.config.sentiment
        in_window = [
            review
            for review in reviews
            if 0
            <= (as_of - review.published_at.date()).days
            <= config.comparison_window_days
        ]
        if len(in_window) < config.min_reviews:
            return SignalResult(False, 0.0, 0.0, "Sentiment için review yetersiz.", {})

        recent: list[float] = []
        older: list[float] = []
        positive_hits = 0
        negative_hits = 0
        for review in in_window:
            score, positives, negatives = self._review_sentiment(review)
            age_days = (as_of - review.published_at.date()).days
            positive_hits += positives
            negative_hits += negatives
            if age_days <= config.recent_window_days:
                recent.append(score)
            else:
                older.append(score)

        if not recent:
            return SignalResult(
                False, 0.0, 0.0, "Yakın dönem sentiment verisi yok.", {}
            )
        recent_mean = statistics.fmean(recent)
        if older:
            older_mean = statistics.fmean(older)
            sentiment_delta = recent_mean - older_mean
            value = _clip(sentiment_delta / config.full_scale_sentiment_delta)
            reliability = min(1.0, len(in_window) / 10)
            mode = "drift"
        else:
            older_mean = None
            sentiment_delta = recent_mean
            value = _clip(recent_mean)
            reliability = min(0.4, len(recent) / 10)
            mode = "recent_level_proxy"
        direction = (
            "iyileşiyor" if value > 0.05 else "zayıflıyor" if value < -0.05 else "yatay"
        )
        return SignalResult(
            True,
            value,
            reliability,
            f"Review sentiment görünümü {direction}.",
            {
                "recent_mean": round(recent_mean, 4),
                "older_mean": round(older_mean, 4) if older_mean is not None else None,
                "sentiment_delta": round(sentiment_delta, 4),
                "review_count": len(in_window),
                "positive_keyword_hits": positive_hits,
                "negative_keyword_hits": negative_hits,
                "mode": mode,
            },
        )

    def _review_sentiment(self, review: ReviewInput) -> tuple[float, int, int]:
        text = _normalized_text(review.text)
        positives = sum(
            len(pattern.findall(text)) for pattern in self._positive_patterns
        )
        negatives = sum(
            len(pattern.findall(text)) for pattern in self._negative_patterns
        )
        total_hits = positives + negatives
        if total_hits:
            score = (positives - negatives) / total_hits
        else:
            score = (review.rating - 3) / 2
        return _clip(score), positives, negatives

    def _stability(
        self,
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
    ) -> SignalResult:
        config = self.config.stability
        as_of = snapshots[-1].snapshot_date
        if config.review_stability_enabled:
            review_based = self._stability_from_reviews(
                snapshots, reviews, config=config, as_of=as_of
            )
            if review_based is not None:
                return review_based
        window = [
            snapshot
            for snapshot in snapshots
            if snapshot.rating is not None
            and 0 <= (as_of - snapshot.snapshot_date).days <= config.window_days
        ]
        coverage_days = (
            (window[-1].snapshot_date - window[0].snapshot_date).days if window else 0
        )
        if (
            len(window) < config.min_snapshots
            or coverage_days < config.min_coverage_days
        ):
            return SignalResult(
                False,
                0.0,
                0.0,
                "İstikrar için periyodik snapshot birikiyor.",
                {
                    "state": "insufficient_data",
                    "snapshot_count": len(window),
                    "coverage_days": coverage_days,
                },
            )
        ratings = [float(snapshot.rating) for snapshot in window]
        mean_rating = statistics.fmean(ratings)
        rating_stddev = statistics.pstdev(ratings)
        reliability = min(
            1.0,
            len(window) / self.config.confidence.full_history_snapshots,
            coverage_days / self.config.confidence.full_history_days,
        )
        if rating_stddev > config.max_rating_stddev:
            state = "volatile"
            base_value = config.volatile_value
            base_summary = "Rating seviyesi dalgalı."
        elif mean_rating >= config.high_rating_threshold:
            state = "stable_high"
            base_value = config.stable_high_value
            base_summary = "Yüksek rating seviyesini istikrarlı koruyor."
        else:
            state = "stable_low"
            base_value = config.stable_low_value
            base_summary = "Düşük/orta rating seviyesinde durağan."

        days_since_activity = self._days_since_activity(snapshots, reviews, as_of)
        dormancy_penalty = self._dormancy_penalty(days_since_activity, config)
        value = base_value + dormancy_penalty
        summary = base_summary
        if dormancy_penalty < 0:
            summary = (
                f"{base_summary} Son {days_since_activity} gündür yeni oy/yorum yok, "
                "bu skoru geriletiyor."
            )
        if (
            days_since_activity is not None
            and days_since_activity >= config.dormancy_full_penalty_days
        ):
            state = "dormant"
            summary = (
                f"Yaklaşık {days_since_activity} gündür yeni oy/yorum yok; "
                "mekan sessizleşti."
            )

        return SignalResult(
            True,
            _clip(value),
            reliability,
            summary,
            {
                "state": state,
                "mean_rating": round(mean_rating, 4),
                "rating_stddev": round(rating_stddev, 4),
                "snapshot_count": len(window),
                "coverage_days": coverage_days,
                "window_days": config.window_days,
                "days_since_activity": days_since_activity,
                "dormancy_penalty": round(dormancy_penalty, 4),
            },
        )

    def _stability_from_reviews(
        self,
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
        *,
        config: StabilityConfig,
        as_of: date,
    ) -> SignalResult | None:
        """Stability from the review corpus, or None when it is too thin.

        Instead of waiting for many aggregate snapshots, this reads how much the
        rating LEVEL moves across time-ordered buckets of the review sequence: a
        venue whose reviews hover near 4.2 the whole way through reads as stable
        now; one whose bucket means swing reads as volatile. Dormancy (no recent
        activity) still applies exactly as in the snapshot path.
        """
        rated = sorted(
            (review for review in reviews if review.rating is not None),
            key=lambda review: review.published_at,
        )
        if len(rated) < config.review_min_for_stability:
            return None
        buckets = [
            bucket
            for bucket in self._even_chunks(
                [review.rating for review in rated], config.review_stability_buckets
            )
            if bucket
        ]
        if len(buckets) < 2:
            return None
        bucket_means = [statistics.fmean(bucket) for bucket in buckets]
        mean_rating = statistics.fmean([review.rating for review in rated])
        level_stddev = statistics.pstdev(bucket_means)
        reliability = min(1.0, len(rated) / config.review_full_reliability_count)
        coverage_days = (
            rated[-1].published_at.date() - rated[0].published_at.date()
        ).days

        if level_stddev > config.review_max_level_stddev:
            state = "volatile"
            base_value = config.volatile_value
            base_summary = "Rating seviyesi yorumlar boyunca dalgalı."
        elif mean_rating >= config.high_rating_threshold:
            state = "stable_high"
            base_value = config.stable_high_value
            base_summary = (
                "Yüksek rating seviyesini yorumlar boyunca istikrarlı koruyor."
            )
        else:
            state = "stable_low"
            base_value = config.stable_low_value
            base_summary = "Rating seviyesi durağan (orta/düşük)."

        days_since_activity = self._days_since_activity(snapshots, reviews, as_of)
        dormancy_penalty = self._dormancy_penalty(days_since_activity, config)
        value = base_value + dormancy_penalty
        summary = base_summary
        if dormancy_penalty < 0:
            summary = (
                f"{base_summary} Son {days_since_activity} gündür yeni oy/yorum yok, "
                "bu skoru geriletiyor."
            )
        if (
            days_since_activity is not None
            and days_since_activity >= config.dormancy_full_penalty_days
        ):
            state = "dormant"
            summary = (
                f"Yaklaşık {days_since_activity} gündür yeni oy/yorum yok; "
                "mekan sessizleşti."
            )

        return SignalResult(
            True,
            _clip(value),
            reliability,
            summary,
            {
                "state": state,
                "mode": "review_consistency",
                "mean_rating": round(mean_rating, 4),
                "level_stddev": round(level_stddev, 4),
                "bucket_count": len(bucket_means),
                "review_count": len(rated),
                "coverage_days": coverage_days,
                "days_since_activity": days_since_activity,
                "dormancy_penalty": round(dormancy_penalty, 4),
            },
        )

    @staticmethod
    def _even_chunks(items: list[int], count: int) -> list[list[int]]:
        """Split items into `count` contiguous, roughly-equal buckets in order."""
        if count <= 1 or len(items) <= 1:
            return [items]
        base, remainder = divmod(len(items), count)
        chunks: list[list[int]] = []
        start = 0
        for index in range(count):
            size = base + (1 if index < remainder else 0)
            if size == 0:
                continue
            chunks.append(items[start : start + size])
            start += size
        return chunks

    @staticmethod
    def _days_since_activity(
        snapshots: list[PlaceSnapshot],
        reviews: list[ReviewInput],
        as_of: date,
    ) -> int | None:
        """Days since the last observed rating-count growth or new review.

        Rating-count growth (user_ratings_total increasing) counts as
        activity even with no new review text, since a venue can still be
        actively rated without anyone writing a review.
        """
        last_growth_date = None
        for previous, current in pairwise(snapshots):
            if (
                previous.user_ratings_total is not None
                and current.user_ratings_total is not None
                and current.user_ratings_total > previous.user_ratings_total
            ):
                last_growth_date = current.snapshot_date
        last_review_date = max(
            (review.published_at.date() for review in reviews), default=None
        )
        candidates = [
            value for value in (last_growth_date, last_review_date) if value is not None
        ]
        if candidates:
            return (as_of - max(candidates)).days
        # No growth or review has ever been observed in the entire snapshot
        # history -- this is itself evidence of inactivity, not a reason to
        # skip the penalty. Anchor to the earliest snapshot we have.
        return (as_of - snapshots[0].snapshot_date).days

    @staticmethod
    def _dormancy_penalty(
        days_since_activity: int | None,
        config: StabilityConfig,
    ) -> float:
        if (
            days_since_activity is None
            or days_since_activity <= config.dormancy_grace_days
        ):
            return 0.0
        ramp_span = config.dormancy_full_penalty_days - config.dormancy_grace_days
        progress = min(
            1.0, (days_since_activity - config.dormancy_grace_days) / ramp_span
        )
        return config.dormancy_penalty_value * progress

    def _classification(self, change_score: float) -> str:
        if change_score >= self.config.classification.costu_threshold:
            return "costu"
        if change_score <= self.config.classification.bozdu_threshold:
            return "bozdu"
        return "dengede"

    @staticmethod
    def _change_story(
        classification: str,
        change_score: float,
        confidence: float,
        signals: dict[str, SignalResult],
    ) -> str:
        if classification == "costu":
            lead = f"Veriler Coştu yönünü gösteriyor ({change_score:+.1f})."
        elif classification == "bozdu":
            lead = f"Veriler Bozdu yönünü gösteriyor ({change_score:+.1f})."
        else:
            lead = f"Değişim skoru şimdilik dengede ({change_score:+.1f})."
        stability = signals["stability"]
        state = stability.details["state"]
        if state == "stable_high":
            days = stability.details["coverage_days"]
            stability_text = (
                f"Son {days} günlük gözlemde yüksek seviyesini istikrarlı koruyor."
            )
        elif state == "stable_low":
            stability_text = "Seviye durağan; bu durum pozitif istikrar sayılmıyor."
        elif state == "volatile":
            stability_text = "Rating seviyesi gözlem penceresinde dalgalı."
        elif state == "dormant":
            days = stability.details["days_since_activity"]
            stability_text = (
                f"Yaklaşık {days} gündür yeni oy/yorum yok; mekan sessizleşti."
            )
        else:
            stability_text = "İstikrar yorumu için periyodik snapshot birikiyor."
        confidence_text = f"Veri güveni %{confidence * 100:.0f}."
        return " ".join((lead, stability_text, confidence_text))
