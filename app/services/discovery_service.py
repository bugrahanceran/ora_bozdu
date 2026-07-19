from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from app.adapters.base import (
    DiscoveryCandidate,
    PlaceDiscoveryProvider,
    ReviewFreshnessProvider,
)
from app.catalog import VenueCatalog, VenueCatalogEntry
from app.data_collection_config import DataCollectionConfig
from app.discovery.selector import (
    apply_hard_filters,
    deduplicate_candidates,
    score_candidate,
    select_candidates,
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
    target_count: int,
    as_of_date: date,
    searched: tuple[DiscoveryCandidate, ...],
    query_counts: dict[str, int],
    freshness_by_place_id: dict[str, datetime | None],
) -> DiscoveryResult:
    existing = existing_catalog.venues
    if target_count <= len(existing):
        catalog = VenueCatalog(
            region_slug=config.region.slug,
            region_name=config.region.name,
            venues=existing,
        )
        return DiscoveryResult(
            catalog=catalog,
            report={
                "as_of_date": as_of_date.isoformat(),
                "target_count": target_count,
                "query_counts": query_counts,
                "candidate_count": len(searched),
                "unique_new_candidate_count": 0,
                "existing_preserved": len(existing),
                "rejected": {
                    "duplicate_or_existing": len(searched),
                    "business_status": 0,
                    "review_count": 0,
                    "brand_cap": 0,
                    "not_selected": 0,
                },
                "freshness_checked": 0,
                "selected_new": 0,
                "catalog_total": len(existing),
                "catalog_categories": dict(
                    sorted(Counter(entry.category for entry in existing).items())
                ),
                "selected": [],
            },
        )
    existing_place_ids = {entry.place_id for entry in existing}
    new_candidates = tuple(
        candidate
        for candidate in searched
        if candidate.place_id not in existing_place_ids
    )
    unique_new_candidates = deduplicate_candidates(new_candidates)
    filtered = apply_hard_filters(
        unique_new_candidates,
        config=config.discovery,
        existing=existing,
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
    selected = select_candidates(
        scored,
        existing=existing,
        target_count=target_count,
        config=config.discovery,
    )
    used_slugs = {entry.slug for entry in existing}
    new_entries: list[VenueCatalogEntry] = []
    for item in selected:
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

    venues = tuple((*existing, *new_entries))
    catalog = VenueCatalog(
        region_slug=config.region.slug,
        region_name=config.region.name,
        venues=venues,
    )
    report = {
        "as_of_date": as_of_date.isoformat(),
        "target_count": target_count,
        "query_counts": query_counts,
        "candidate_count": len(searched),
        "unique_new_candidate_count": len(unique_new_candidates),
        "existing_preserved": len(existing),
        "rejected": {
            "duplicate_or_existing": len(searched) - len(unique_new_candidates),
            "business_status": filtered.rejected_status,
            "review_count": filtered.rejected_review_count,
            "brand_cap": filtered.rejected_brand_cap,
            "not_selected": len(scored) - len(selected),
        },
        "freshness_checked": len(scored),
        "selected_new": len(new_entries),
        "catalog_total": len(venues),
        "catalog_categories": dict(
            sorted(Counter(entry.category for entry in venues).items())
        ),
        "selected": [
            {
                **asdict(entry),
                "selection_score": round(item.score, 6),
                "freshness_state": item.freshness_state,
                "newest_review_at": (
                    item.newest_review_at.isoformat() if item.newest_review_at else None
                ),
            }
            for entry, item in zip(new_entries, selected, strict=True)
        ],
    }
    return DiscoveryResult(catalog=catalog, report=report)


class DiscoveryService:
    def __init__(
        self,
        discovery_provider: PlaceDiscoveryProvider,
        freshness_provider: ReviewFreshnessProvider,
    ) -> None:
        self._discovery_provider = discovery_provider
        self._freshness_provider = freshness_provider

    async def run(
        self,
        *,
        config: DataCollectionConfig,
        existing_catalog: VenueCatalog,
        target_count: int,
        as_of_date: date,
    ) -> DiscoveryResult:
        if target_count <= len(existing_catalog.venues):
            return build_discovery_result(
                config=config,
                existing_catalog=existing_catalog,
                target_count=target_count,
                as_of_date=as_of_date,
                searched=(),
                query_counts={},
                freshness_by_place_id={},
            )
        searched: list[DiscoveryCandidate] = []
        query_counts: dict[str, int] = {}
        for query in config.discovery.queries:
            found = await self._discovery_provider.search(
                category=query.category,
                text_query=query.text_query,
                included_type=query.included_type,
                latitude=config.region.center.latitude,
                longitude=config.region.center.longitude,
                radius_meters=config.discovery.radius_meters,
                page_size=config.discovery.page_size,
            )
            searched.extend(found)
            query_counts[query.category] = len(found)

        existing_place_ids = {entry.place_id for entry in existing_catalog.venues}
        unique_new_candidates = deduplicate_candidates(
            tuple(
                candidate
                for candidate in searched
                if candidate.place_id not in existing_place_ids
            )
        )
        filtered = apply_hard_filters(
            unique_new_candidates,
            config=config.discovery,
            existing=existing_catalog.venues,
        )
        freshness = {}
        for candidate in filtered.candidates:
            result = await self._freshness_provider.fetch_review_freshness(
                candidate.place_id
            )
            freshness[candidate.place_id] = result.latest_review_at

        return build_discovery_result(
            config=config,
            existing_catalog=existing_catalog,
            target_count=target_count,
            as_of_date=as_of_date,
            searched=tuple(searched),
            query_counts=query_counts,
            freshness_by_place_id=freshness,
        )
