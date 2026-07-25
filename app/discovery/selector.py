import math
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalogEntry
from app.data_collection_config import DiscoveryConfig, RegionConfig
from app.discovery.geo import distance_meters


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
    rejected_outside_radius: int
    rejected_irrelevant_primary_type: int


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
    region: RegionConfig,
) -> FilterResult:
    rejected_status = 0
    rejected_review_count = 0
    rejected_outside_radius = 0
    rejected_irrelevant_primary_type = 0
    accepted: list[DiscoveryCandidate] = []
    for candidate in deduplicate_candidates(candidates):
        if candidate.business_status != "OPERATIONAL":
            rejected_status += 1
            continue
        if candidate.primary_type in config.excluded_primary_types:
            rejected_irrelevant_primary_type += 1
            continue
        if candidate.user_ratings_total < config.min_user_ratings_total:
            rejected_review_count += 1
            continue
        if (
            distance_meters(
                origin_latitude=region.center.latitude,
                origin_longitude=region.center.longitude,
                destination_latitude=candidate.latitude,
                destination_longitude=candidate.longitude,
            )
            > config.radius_meters
        ):
            rejected_outside_radius += 1
            continue
        accepted.append(candidate)

    return FilterResult(
        candidates=tuple(sorted(accepted, key=lambda item: item.place_id)),
        rejected_status=rejected_status,
        rejected_review_count=rejected_review_count,
        rejected_outside_radius=rejected_outside_radius,
        rejected_irrelevant_primary_type=rejected_irrelevant_primary_type,
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


def accept_all_candidates(
    scored: tuple[ScoredCandidate, ...],
) -> tuple[ScoredCandidate, ...]:
    """Every scored candidate, ordered for a readable report -- no selection cutoff."""
    return tuple(
        sorted(scored, key=lambda item: (-item.score, item.candidate.place_id))
    )


def rank_tracked_venues(
    entries: tuple[VenueCatalogEntry, ...],
    *,
    current_review_counts: dict[str, int],
    limit: int,
) -> tuple[VenueCatalogEntry, ...]:
    """Re-rank the catalog by review count and mark the top `limit` as tracked.

    Every entry's `user_ratings_total` is refreshed from this round's scan
    when available, else it keeps its last known value. Entries with a known
    count (this round or a previous one) compete for the top `limit` tracked
    slots purely by that count -- no protection for newly-discovered venues,
    per an explicit product decision (Google Places has no opening-date
    field, so there's no reliable "how new is this place" signal to protect
    on anyway). Entries with no count at all (never scanned, never fetched)
    keep whatever `tracked` state they already had -- there's no data to
    rank them by, so they're neither promoted nor demoted. List order is
    preserved; only `tracked` and `user_ratings_total` are updated.
    """
    updated_counts = {
        entry.place_id: current_review_counts.get(
            entry.place_id, entry.user_ratings_total
        )
        for entry in entries
    }
    ranked = sorted(
        (
            (place_id, count)
            for place_id, count in updated_counts.items()
            if count is not None
        ),
        key=lambda item: (-item[1], item[0]),
    )
    tracked_place_ids = {place_id for place_id, _ in ranked[:limit]}

    result: list[VenueCatalogEntry] = []
    for entry in entries:
        count = updated_counts[entry.place_id]
        if count is None:
            tracked = entry.tracked
        else:
            tracked = entry.place_id in tracked_place_ids
        result.append(replace(entry, tracked=tracked, user_ratings_total=count))
    return tuple(result)
