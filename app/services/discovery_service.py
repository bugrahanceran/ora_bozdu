from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from app.adapters.base import DiscoveryCandidate
from app.catalog import VenueCatalog, VenueCatalogEntry
from app.data_collection_config import DataCollectionConfig
from app.discovery.selector import (
    accept_all_candidates,
    apply_hard_filters,
    deduplicate_candidates,
    rank_tracked_venues,
    score_candidate,
    slugify,
)


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    catalog: VenueCatalog
    report: dict[str, Any]


def build_discovery_result(
    *,
    config: DataCollectionConfig,
    existing_catalog: VenueCatalog,
    as_of_date: date,
    searched: tuple[DiscoveryCandidate, ...],
    grid_summary: dict[str, int],
    freshness_by_place_id: dict[str, datetime | None],
    all_scanned_candidates: tuple[DiscoveryCandidate, ...],
) -> DiscoveryResult:
    existing = existing_catalog.venues
    existing_place_ids = {entry.place_id for entry in existing}
    new_candidates = tuple(
        candidate
        for candidate in searched
        if candidate.place_id not in existing_place_ids
    )
    unique_new_candidates = deduplicate_candidates(new_candidates)
    filtered = apply_hard_filters(
        unique_new_candidates, config=config.discovery, region=config.region
    )
    missing_freshness = {
        candidate.place_id for candidate in filtered.candidates
    } - freshness_by_place_id.keys()
    if missing_freshness:
        raise ValueError(
            f"Freshness stage is incomplete for {len(missing_freshness)} candidates"
        )
    scored = tuple(
        score_candidate(
            candidate,
            newest_review_at=freshness_by_place_id[candidate.place_id],
            as_of_date=as_of_date,
            config=config.discovery,
        )
        for candidate in filtered.candidates
    )
    added = accept_all_candidates(scored)
    used_slugs = {entry.slug for entry in existing}
    new_entries: list[VenueCatalogEntry] = []
    for item in added:
        slug = slugify(item.candidate.display_name, item.candidate.place_id)
        if slug in used_slugs:
            slug = f"{slug}-{item.candidate.place_id[:8].casefold()}"
        used_slugs.add(slug)
        new_entries.append(
            VenueCatalogEntry(
                slug=slug,
                display_name=item.candidate.display_name,
                place_id=item.candidate.place_id,
                category=item.candidate.category,
                brand_key=item.brand_key,
            )
        )

    current_review_counts = {
        candidate.place_id: candidate.user_ratings_total
        for candidate in all_scanned_candidates
    }
    venues = rank_tracked_venues(
        tuple((*existing, *new_entries)),
        current_review_counts=current_review_counts,
        limit=config.discovery.tracked_venue_limit,
    )
    ranked_new_entries = venues[len(existing) :]
    catalog = VenueCatalog(
        region_slug=config.region.slug,
        region_name=config.region.name,
        venues=venues,
    )
    report = {
        "as_of_date": as_of_date.isoformat(),
        "grid_summary": grid_summary,
        "candidate_count": len(searched),
        "unique_new_candidate_count": len(unique_new_candidates),
        "existing_preserved": len(existing),
        "rejected": {
            "duplicate_or_existing": len(searched) - len(unique_new_candidates),
            "business_status": filtered.rejected_status,
            "irrelevant_primary_type": filtered.rejected_irrelevant_primary_type,
            "review_count": filtered.rejected_review_count,
            "outside_radius": filtered.rejected_outside_radius,
        },
        "freshness_checked": len(scored),
        "added_count": len(new_entries),
        "catalog_total": len(venues),
        "tracked_count": sum(1 for entry in venues if entry.tracked),
        "not_tracked_count": sum(1 for entry in venues if not entry.tracked),
        "catalog_categories": dict(
            sorted(Counter(entry.category for entry in venues).items())
        ),
        "added": [
            {
                **asdict(entry),
                "selection_score": round(item.score, 6),
                "freshness_state": item.freshness_state,
                "newest_review_at": (
                    item.newest_review_at.isoformat() if item.newest_review_at else None
                ),
            }
            for entry, item in zip(ranked_new_entries, added, strict=True)
        ],
    }
    return DiscoveryResult(catalog=catalog, report=report)
