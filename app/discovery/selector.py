import math
import re
import unicodedata
from collections import Counter, defaultdict
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
    rejected_brand_cap: int


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
    by_place_id: dict[str, DiscoveryCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.place_id,
            item.primary_type != item.category,
            item.category,
        ),
    ):
        by_place_id.setdefault(candidate.place_id, candidate)
    return tuple(by_place_id[place_id] for place_id in sorted(by_place_id))


def apply_hard_filters(
    candidates: tuple[DiscoveryCandidate, ...],
    *,
    config: DiscoveryConfig,
    existing: tuple[VenueCatalogEntry, ...],
) -> FilterResult:
    rejected_status = 0
    rejected_review_count = 0
    eligible: list[tuple[DiscoveryCandidate, str]] = []
    for candidate in deduplicate_candidates(candidates):
        if candidate.business_status != "OPERATIONAL":
            rejected_status += 1
            continue
        if candidate.user_ratings_total < config.min_user_ratings_total:
            rejected_review_count += 1
            continue
        brand_key = normalize_brand(
            candidate.display_name,
            stopwords=config.brand_stopwords,
            aliases=config.brand_aliases,
        )
        eligible.append((candidate, brand_key))

    existing_brand_counts = Counter(entry.brand_key for entry in existing)
    grouped: dict[str, list[DiscoveryCandidate]] = defaultdict(list)
    for candidate, brand_key in eligible:
        grouped[brand_key].append(candidate)

    accepted: list[DiscoveryCandidate] = []
    rejected_brand_cap = 0
    for brand_key in sorted(grouped):
        slots = max(
            0,
            config.max_branches_per_brand - existing_brand_counts[brand_key],
        )
        ranked = sorted(
            grouped[brand_key],
            key=lambda item: (-item.user_ratings_total, item.place_id),
        )
        accepted.extend(ranked[:slots])
        rejected_brand_cap += len(ranked[slots:])

    return FilterResult(
        candidates=tuple(sorted(accepted, key=lambda item: item.place_id)),
        rejected_status=rejected_status,
        rejected_review_count=rejected_review_count,
        rejected_brand_cap=rejected_brand_cap,
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
    config: DiscoveryConfig,
) -> tuple[ScoredCandidate, ...]:
    if target_count < sum(config.category_minimums.values()):
        raise DiscoverySelectionError("target_count is below category minimums")
    needed = max(0, target_count - len(existing))
    if needed == 0:
        return ()

    ranked = sorted(scored, key=lambda item: (-item.score, item.candidate.place_id))
    selected: list[ScoredCandidate] = []
    selected_ids: set[str] = set()
    existing_categories = Counter(entry.category for entry in existing)

    for category, minimum in config.category_minimums.items():
        category_needed = max(0, minimum - existing_categories[category])
        available = [
            item
            for item in ranked
            if item.candidate.category == category
            and item.candidate.place_id not in selected_ids
        ]
        if len(available) < category_needed:
            raise DiscoverySelectionError(
                f"Not enough {category!r} candidates for configured quota"
            )
        for item in available[:category_needed]:
            selected.append(item)
            selected_ids.add(item.candidate.place_id)

    remaining_slots = needed - len(selected)
    if remaining_slots < 0:
        raise DiscoverySelectionError("existing category deficits exceed target slots")
    remaining = [item for item in ranked if item.candidate.place_id not in selected_ids]
    if len(remaining) < remaining_slots:
        raise DiscoverySelectionError("Not enough candidates to reach target_count")
    selected.extend(remaining[:remaining_slots])
    return tuple(selected)
