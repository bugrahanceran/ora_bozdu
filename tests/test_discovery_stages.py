from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.adapters.base import (
    DiscoveryCandidate,
    NearbySearchCellResult,
    RawPlacePayload,
    ReviewFreshnessResult,
)
from app.catalog import VenueCatalog
from app.data_collection_config import load_data_collection_config
from app.discovery.search_cache import (
    CachedCandidate,
    DiscoverySearchCache,
    GridCellState,
    load_search_cache,
    write_search_cache,
)
from app.services.discovery_stages import (
    DiscoveryFreshnessStage,
    DiscoveryGridSearchStage,
)

CONFIG_PATH = Path("config/data_collection.eryaman.yaml")


def _candidate(place_id: str, count: int = 500) -> DiscoveryCandidate:
    return DiscoveryCandidate(
        place_id=place_id,
        display_name=f"{place_id} Venue",
        category="restaurant",
        business_status="OPERATIONAL",
        user_ratings_total=count,
        primary_type="restaurant",
        latitude=39.979,
        longitude=32.636,
    )


def _pending_cell(
    cell_id: str,
    *,
    radius: float = 500.0,
    depth: int = 0,
    parent_cell_id: str | None = None,
) -> GridCellState:
    return GridCellState(
        cell_id=cell_id,
        center_latitude=39.979,
        center_longitude=32.636,
        radius_meters=radius,
        included_types=("restaurant",),
        depth=depth,
        parent_cell_id=parent_cell_id,
    )


def _searched_cell(cell_id: str) -> GridCellState:
    cell = _pending_cell(cell_id)
    cell.status = "searched"
    cell.result_count = 0
    cell.searched_at = datetime(2026, 7, 19, tzinfo=UTC)
    return cell


def _cache(cells: list[GridCellState], **overrides) -> DiscoverySearchCache:
    defaults = dict(
        collection_config_hash="config-hash",
        catalog_hash="catalog-hash",
        region_slug="eryaman",
        as_of_date=date(2026, 7, 19),
        cells=cells,
    )
    defaults.update(overrides)
    return DiscoverySearchCache(**defaults)


class FakeNearbySearchProvider:
    provider_name = "places_api_new"

    def __init__(self, results: list[tuple[list[str], bool]]) -> None:
        self._results = list(results)
        self.calls: list[dict] = []

    async def search_cell(self, **kwargs) -> NearbySearchCellResult:
        self.calls.append(kwargs)
        place_ids, hit_cap = self._results.pop(0)
        candidates = tuple(_candidate(place_id) for place_id in place_ids)
        return NearbySearchCellResult(
            candidates=candidates,
            fetched_at=datetime(2026, 7, 19, tzinfo=UTC),
            raw_payload={"places": [{"id": place_id} for place_id in place_ids]},
            hit_result_cap=hit_cap,
        )

    async def aclose(self) -> None:
        return None


class FakeFreshnessProvider:
    provider_name = "places_api"

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_review_freshness(self, place_id: str) -> ReviewFreshnessResult:
        self.calls.append(place_id)
        latest = datetime(2026, 7, 18, tzinfo=UTC)
        return ReviewFreshnessResult(
            latest_review_at=latest,
            payload=RawPlacePayload(
                request_variant="details_newest",
                review_sort="newest",
                fetched_at=latest,
                body={"status": "OK", "result": {"reviews": []}},
                payload_hash=f"hash-{place_id}",
            ),
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_grid_search_stage_honors_request_budget_and_resumes(
    tmp_path: Path,
) -> None:
    config = load_data_collection_config(CONFIG_PATH)
    cache = _cache(
        [_pending_cell("r0c0"), _pending_cell("r0c1"), _pending_cell("r0c2")]
    )
    provider = FakeNearbySearchProvider(
        [(["a"], False), (["b"], False), (["c"], False)]
    )
    cache_path = tmp_path / "search-cache.json"
    stage = DiscoveryGridSearchStage(provider)

    first = await stage.run(
        cache=cache,
        config=config,
        max_requests=1,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert first.requests_this_run == 1
    assert first.search_completed is False
    assert first.cells_searched == 1
    assert first.cells_pending == 2
    persisted = load_search_cache(cache_path)

    second = await stage.run(
        cache=persisted,
        config=config,
        max_requests=5,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert second.requests_this_run == 2
    assert second.search_completed is True
    assert second.total_cells == 3
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_grid_search_stage_accepts_a_capped_cell_without_splitting() -> None:
    # A cell hitting the result cap (20) used to trigger a one-level split
    # into 4 sub-cells; this was removed (2026-07-24, product decision) in
    # favor of a predictable, fixed request count -- the cell's (possibly
    # truncated) result is now simply accepted as final and flagged.
    config = load_data_collection_config(CONFIG_PATH)
    cache = _cache([_pending_cell("r0c0")])
    provider = FakeNearbySearchProvider([([f"p{i}" for i in range(20)], True)])

    summary = await DiscoveryGridSearchStage(provider).run(
        cache=cache,
        config=config,
        max_requests=1,
        checkpoint=lambda value: None,
    )

    assert summary.search_completed is True
    assert len(cache.cells) == 1
    assert cache.cells[0].status == "searched"
    assert cache.cells[0].hit_result_cap is True
    assert summary.cells_flagged_for_review == 1


def test_cells_flagged_for_review_ignores_historical_split_parents() -> None:
    # Backward compatibility with caches from before splitting was removed:
    # a "split" parent that hit the cap was superseded by its children and
    # must not be flagged; only a terminal ("searched") capped cell should.
    split_parent = _pending_cell("r0c0")
    split_parent.status = "split"
    split_parent.hit_result_cap = True
    resolved_child = _searched_cell("r0c0.nw")
    resolved_child.hit_result_cap = False
    capped_child = _searched_cell("r0c0.ne")
    capped_child.hit_result_cap = True
    cache = _cache([split_parent, resolved_child, capped_child])

    assert [cell.cell_id for cell in cache.cells_flagged_for_review] == ["r0c0.ne"]


@pytest.mark.asyncio
async def test_freshness_stage_honors_request_budget(tmp_path: Path) -> None:
    config = load_data_collection_config(CONFIG_PATH)
    catalog = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    cache = _cache(
        [_searched_cell("r0c0.batch0")],
        candidates=[
            CachedCandidate.from_domain(_candidate("cafe-a")),
            CachedCandidate.from_domain(_candidate("cafe-b")),
            CachedCandidate.from_domain(_candidate("restaurant-a")),
        ],
    )
    freshness_provider = FakeFreshnessProvider()
    cache_path = tmp_path / "search-cache.json"

    summary = await DiscoveryFreshnessStage(freshness_provider).run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=1,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert summary.requests_this_run == 1
    assert summary.freshness_required == 3
    assert summary.freshness_completed == 1
    assert summary.freshness_remaining == 2
    assert freshness_provider.calls == ["cafe-a"]
    assert cache.freshness_payloads["cafe-a"].review_sort == "newest"


@pytest.mark.asyncio
async def test_freshness_stage_skips_cross_region_place_ids() -> None:
    config = load_data_collection_config(CONFIG_PATH)
    catalog = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    cache = _cache(
        [_searched_cell("r0c0.batch0")],
        candidates=[
            CachedCandidate.from_domain(_candidate("cafe-a")),
            CachedCandidate.from_domain(_candidate("other-region-place")),
        ],
    )
    freshness_provider = FakeFreshnessProvider()

    summary = await DiscoveryFreshnessStage(freshness_provider).run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=5,
        checkpoint=lambda value: None,
        cross_region_place_ids=frozenset({"other-region-place"}),
    )

    assert summary.freshness_required == 1
    assert freshness_provider.calls == ["cafe-a"]
