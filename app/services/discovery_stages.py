from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.adapters.base import NearbySearchProvider, ReviewFreshnessProvider
from app.catalog import VenueCatalog
from app.data_collection_config import DataCollectionConfig
from app.discovery.search_cache import (
    CachedCandidate,
    CachedFreshnessPayload,
    CellSearchRecord,
    DiscoverySearchCache,
)
from app.discovery.selector import apply_hard_filters, deduplicate_candidates

Checkpoint = Callable[[DiscoverySearchCache], None]


@dataclass(frozen=True, slots=True)
class GridSearchStageSummary:
    requests_this_run: int
    total_search_requests: int
    search_completed: bool
    total_cells: int
    cells_searched: int
    cells_pending: int
    cells_split: int
    cells_flagged_for_review: int
    raw_candidates: int


@dataclass(frozen=True, slots=True)
class FreshnessStageSummary:
    requests_this_run: int
    freshness_required: int
    freshness_completed: int
    freshness_remaining: int


def _filtered_candidates(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
    cross_region_place_ids: frozenset[str] = frozenset(),
):
    existing_place_ids = {
        entry.place_id for entry in catalog.venues
    } | cross_region_place_ids
    new_candidates = tuple(
        candidate
        for candidate in cache.domain_candidates()
        if candidate.place_id not in existing_place_ids
    )
    unique_candidates = deduplicate_candidates(new_candidates)
    filtered = apply_hard_filters(
        unique_candidates, config=config.discovery, region=config.region
    )
    return unique_candidates, filtered


def freshness_shortlist(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
    cross_region_place_ids: frozenset[str] = frozenset(),
):
    """Every locally-eligible candidate that still needs a freshness check.

    Not narrowed by any target size: every hard-filter-passing candidate gets
    added to the catalog, so every one of them needs a real freshness result.
    """
    _, filtered = _filtered_candidates(
        cache,
        config=config,
        catalog=catalog,
        cross_region_place_ids=cross_region_place_ids,
    )
    return filtered.candidates


def grid_search_stage_summary(
    cache: DiscoverySearchCache,
    *,
    requests_this_run: int,
) -> GridSearchStageSummary:
    return GridSearchStageSummary(
        requests_this_run=requests_this_run,
        total_search_requests=cache.total_search_requests,
        search_completed=cache.search_completed,
        total_cells=len(cache.cells),
        cells_searched=sum(1 for cell in cache.cells if cell.status == "searched"),
        cells_pending=sum(1 for cell in cache.cells if cell.status == "pending"),
        cells_split=sum(1 for cell in cache.cells if cell.status == "split"),
        cells_flagged_for_review=len(cache.cells_flagged_for_review),
        raw_candidates=len(cache.candidates),
    )


class DiscoveryGridSearchStage:
    def __init__(self, provider: NearbySearchProvider) -> None:
        self._provider = provider

    async def run(
        self,
        *,
        cache: DiscoverySearchCache,
        config: DataCollectionConfig,
        max_requests: int,
        checkpoint: Checkpoint,
    ) -> GridSearchStageSummary:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        requests_made = 0
        while requests_made < max_requests:
            pending = next(
                (cell for cell in cache.cells if cell.status == "pending"), None
            )
            if pending is None:
                break
            result = await self._provider.search_cell(
                latitude=pending.center_latitude,
                longitude=pending.center_longitude,
                radius_meters=pending.radius_meters,
                included_types=pending.included_types,
                excluded_types=config.discovery.excluded_types,
                rank_preference=config.discovery.rank_preference,
                max_result_count=config.discovery.max_result_count,
            )
            pending.status = "searched"
            pending.result_count = len(result.candidates)
            pending.hit_result_cap = result.hit_result_cap
            pending.searched_at = result.fetched_at
            cache.candidates.extend(
                CachedCandidate.from_domain(candidate)
                for candidate in result.candidates
            )
            cache.cell_search_records.append(
                CellSearchRecord(
                    cell_id=pending.cell_id,
                    fetched_at=result.fetched_at,
                    candidate_count=len(result.candidates),
                    hit_result_cap=result.hit_result_cap,
                    raw_payload=result.raw_payload,
                )
            )
            requests_made += 1
            checkpoint(cache)

        return grid_search_stage_summary(cache, requests_this_run=requests_made)


class DiscoveryFreshnessStage:
    def __init__(self, provider: ReviewFreshnessProvider) -> None:
        self._provider = provider

    async def run(
        self,
        *,
        cache: DiscoverySearchCache,
        config: DataCollectionConfig,
        catalog: VenueCatalog,
        max_requests: int,
        checkpoint: Checkpoint,
        cross_region_place_ids: frozenset[str] = frozenset(),
    ) -> FreshnessStageSummary:
        if not cache.search_completed:
            raise ValueError("Search stage is not complete")
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        required = tuple(
            sorted(
                freshness_shortlist(
                    cache,
                    config=config,
                    catalog=catalog,
                    cross_region_place_ids=cross_region_place_ids,
                ),
                key=lambda candidate: candidate.place_id,
            )
        )
        requests_made = 0
        for candidate in required:
            if candidate.place_id in cache.freshness_results:
                continue
            result = await self._provider.fetch_review_freshness(candidate.place_id)
            cache.freshness_results[candidate.place_id] = (
                result.latest_review_at.isoformat() if result.latest_review_at else None
            )
            cache.freshness_payloads[candidate.place_id] = (
                CachedFreshnessPayload.from_domain(result.payload)
            )
            requests_made += 1
            checkpoint(cache)
            if requests_made >= max_requests:
                break

        completed = sum(
            candidate.place_id in cache.freshness_results for candidate in required
        )
        return FreshnessStageSummary(
            requests_this_run=requests_made,
            freshness_required=len(required),
            freshness_completed=completed,
            freshness_remaining=len(required) - completed,
        )


def summary_dict(summary: GridSearchStageSummary | FreshnessStageSummary) -> dict:
    return asdict(summary)
