import math
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalogEntry
from app.data_collection_config import DiscoveryConfig


class DiscoverySelectionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ScoredCandidate:
    candidate: DiscoveryCandidate
    brand_key: str
    newest_review_at: datetime | None
    freshness_state: str
    score: float


@dataclass(frozen=True, slots=True)
class FilterResult:
    candidates: tuple[DiscoveryCandidate, ...]
    rejected_status: int
    rejected_review_count: int


def _normalized_words(value: str) -> list[str]:
    value = value.replace("ı", "i").replace("İ", "I")
    ascii_value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    )
    return re.findall(r"[a-z0-9]+", ascii_value.casefold())


def normalize_brand(
    display_name: str,
    *,
    stopwords: tuple[str, ...],
    aliases: dict[str, str],
) -> str:
    words = _normalized_words(display_name)
    normalized_stopwords = {
        word for value in stopwords for word in _normalized_words(value)
    }
    while words and words[-1] in normalized_stopwords:
        words.pop()
    brand = "-".join(words) or "unknown-brand"
    normalized_aliases = {
        "-".join(_normalized_words(key)): "-".join(_normalized_words(value))
        for key, value in aliases.items()
    }
    return normalized_aliases.get(brand, brand)


def slugify(display_name: str, place_id: str) -> str:
    slug = "-".join(_normalized_words(display_name))
    return slug or f"venue-{place_id[:8].casefold()}"


def deduplicate_candidates(
    candidates: tuple[DiscoveryCandidate, ...],
) -> tuple[DiscoveryCandidate, ...]:
    by_place_id = {candidate.place_id: candidate for candidate in candidates}
    return tuple(by_place_id[place_id] for place_id in sorted(by_place_id))


def apply_hard_filters(
    candidates: tuple[DiscoveryCandidate, ...],
    *,
    config: DiscoveryConfig,
) -> FilterResult:
    rejected_status = 0
    rejected_review_count = 0
    accepted: list[DiscoveryCandidate] = []
    for candidate in deduplicate_candidates(candidates):
        if candidate.business_status != "OPERATIONAL":
            rejected_status += 1
            continue
        if candidate.user_ratings_total < config.min_user_ratings_total:
            rejected_review_count += 1
            continue
        accepted.append(candidate)

    return FilterResult(
        candidates=tuple(sorted(accepted, key=lambda item: item.place_id)),
        rejected_status=rejected_status,
        rejected_review_count=rejected_review_count,
    )


def score_candidate(
    candidate: DiscoveryCandidate,
    *,
    newest_review_at: datetime | None,
    as_of_date: date,
    config: DiscoveryConfig,
) -> ScoredCandidate:
    if newest_review_at is None:
        freshness_state = "no_recent_review_data"
        freshness_adjustment = -config.stale_penalty
    else:
        review_date = newest_review_at.astimezone(UTC).date()
        age_days = max(0, (as_of_date - review_date).days)
        if age_days >= config.stale_after_days:
            freshness_state = "stale"
            freshness_adjustment = -config.stale_penalty
        else:
            freshness_state = "fresh"
            freshness_adjustment = 0.0
    score = (
        config.review_count_log_weight * math.log1p(candidate.user_ratings_total)
        + freshness_adjustment
    )
    return ScoredCandidate(
        candidate=candidate,
        brand_key=normalize_brand(
            candidate.display_name,
            stopwords=config.brand_stopwords,
            aliases=config.brand_aliases,
        ),
        newest_review_at=newest_review_at,
        freshness_state=freshness_state,
        score=score,
    )


def select_candidates(
    scored: tuple[ScoredCandidate, ...],
    *,
    existing: tuple[VenueCatalogEntry, ...],
    target_count: int,
) -> tuple[ScoredCandidate, ...]:
    needed = max(0, target_count - len(existing))
    if needed == 0:
        return ()

    ranked = sorted(scored, key=lambda item: (-item.score, item.candidate.place_id))
    if len(ranked) < needed:
        raise DiscoverySelectionError("Not enough candidates to reach target_count")
    return tuple(ranked[:needed])
