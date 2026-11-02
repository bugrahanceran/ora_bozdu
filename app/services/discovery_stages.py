from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.adapters.base import NearbySearchProvider
from app.data_collection_config import DataCollectionConfig
from app.discovery.search_cache import (
    CachedCandidate,
    CellSearchRecord,
    DiscoverySearchCache,
)

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


def summary_dict(summary: GridSearchStageSummary) -> dict:
    return asdict(summary)
