from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.adapters.base import (
    DiscoveryCandidate,
    DiscoveryPage,
    RawPlacePayload,
    ReviewFreshnessResult,
)
from app.catalog import VenueCatalog
from app.data_collection_config import DiscoveryQueryConfig, load_data_collection_config
from app.discovery.search_cache import (
    create_search_cache,
    load_search_cache,
    write_search_cache,
)
from app.services.discovery_stages import (
    DiscoveryFreshnessStage,
    DiscoverySearchStage,
)

# These stage-level tests exercise generic multi-query pagination/resumption
# behavior, which the stage still supports even though production config now
# uses a single unified query (see config/data_collection.yaml).
TWO_QUERIES = (
    DiscoveryQueryConfig(category="cafe", text_query="cafe", included_type="cafe"),
    DiscoveryQueryConfig(
        category="restaurant", text_query="restaurant", included_type="restaurant"
    ),
)


def _candidate(place_id: str, category: str, count: int = 500):
    return DiscoveryCandidate(
        place_id=place_id,
        display_name=f"{place_id} Venue",
        category=category,
        business_status="OPERATIONAL",
        user_ratings_total=count,
        primary_type=category,
    )


class FakePagedProvider:
    provider_name = "places_api_new"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def search_page(self, **kwargs) -> DiscoveryPage:
        category = kwargs["category"]
        page_token = kwargs["page_token"]
        self.calls.append((category, page_token))
        if category == "cafe" and page_token is None:
            candidates = (_candidate("cafe-a", "cafe"),)
            next_page_token = "cafe-page-2"
        elif category == "cafe":
            candidates = (_candidate("cafe-b", "cafe"),)
            next_page_token = None
        else:
            candidates = (_candidate("restaurant-a", "restaurant"),)
            next_page_token = None
        return DiscoveryPage(
            candidates=candidates,
            next_page_token=next_page_token,
            fetched_at=datetime(2026, 7, 19, tzinfo=UTC),
            raw_payload={"places": [{"id": item.place_id} for item in candidates]},
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
async def test_search_stage_honors_one_request_budget_and_resumes(
    tmp_path: Path,
) -> None:
    base_config = load_data_collection_config(Path("config/data_collection.yaml"))
    discovery = base_config.discovery.model_copy(
        update={"target_count": 2, "queries": TWO_QUERIES}
    )
    config = base_config.model_copy(update={"discovery": discovery})
    catalog = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    cache = create_search_cache(
        config=config,
        catalog=catalog,
        collection_config_hash="config-hash",
        catalog_hash="catalog-hash",
        target_count=2,
        as_of_date=date(2026, 7, 19),
    )
    cache_path = tmp_path / "search-cache.json"
    provider = FakePagedProvider()
    stage = DiscoverySearchStage(provider)

    first = await stage.run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=1,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert first.requests_this_run == 1
    assert first.search_completed is False
    assert provider.calls == [("cafe", None)]
    persisted = load_search_cache(cache_path)
    assert persisted.queries[0].next_page_token == "cafe-page-2"

    second = await stage.run(
        cache=persisted,
        config=config,
        catalog=catalog,
        max_requests=5,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert second.requests_this_run == 2
    assert second.search_completed is True
    # freshness_shortlist no longer pre-narrows to target_count (2); all 3
    # eligible candidates (cafe-a, cafe-b, restaurant-a) need a freshness
    # check so a stale one can still be out-ranked by a fresher spare.
    assert second.freshness_required == 3
    assert provider.calls == [
        ("cafe", None),
        ("cafe", "cafe-page-2"),
        ("restaurant", None),
    ]


@pytest.mark.asyncio
async def test_search_stage_stops_when_minimum_candidate_pool_is_ready(
    tmp_path: Path,
) -> None:
    base_config = load_data_collection_config(Path("config/data_collection.yaml"))
    discovery = base_config.discovery.model_copy(
        update={
            "target_count": 2,
            "minimum_candidate_pool": 2,
            "queries": TWO_QUERIES,
        }
    )
    config = base_config.model_copy(update={"discovery": discovery})
    catalog = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    cache = create_search_cache(
        config=config,
        catalog=catalog,
        collection_config_hash="config-hash",
        catalog_hash="catalog-hash",
        target_count=2,
        as_of_date=date(2026, 7, 19),
    )
    provider = FakePagedProvider()

    summary = await DiscoverySearchStage(provider).run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=5,
        checkpoint=lambda value: write_search_cache(
            tmp_path / "search-cache.json", value
        ),
    )

    assert summary.requests_this_run == 2
    assert summary.search_completed is True
    assert summary.completion_reason == "minimum_candidate_pool"
    assert summary.eligible_candidate_count == 2
    assert provider.calls == [("cafe", None), ("cafe", "cafe-page-2")]
    assert cache.queries[1].started is False


@pytest.mark.asyncio
async def test_freshness_stage_honors_request_budget(tmp_path: Path) -> None:
    base_config = load_data_collection_config(Path("config/data_collection.yaml"))
    discovery = base_config.discovery.model_copy(
        update={"target_count": 2, "queries": TWO_QUERIES}
    )
    config = base_config.model_copy(update={"discovery": discovery})
    catalog = VenueCatalog(region_slug="eryaman", region_name="Eryaman", venues=())
    cache = create_search_cache(
        config=config,
        catalog=catalog,
        collection_config_hash="config-hash",
        catalog_hash="catalog-hash",
        target_count=2,
        as_of_date=date(2026, 7, 19),
    )
    search_provider = FakePagedProvider()
    cache_path = tmp_path / "search-cache.json"
    await DiscoverySearchStage(search_provider).run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=3,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )
    freshness_provider = FakeFreshnessProvider()

    summary = await DiscoveryFreshnessStage(freshness_provider).run(
        cache=cache,
        config=config,
        catalog=catalog,
        max_requests=1,
        checkpoint=lambda value: write_search_cache(cache_path, value),
    )

    assert summary.requests_this_run == 1
    # All 3 eligible candidates (cafe-a, cafe-b, restaurant-a) require a
    # freshness check now, not just the target_count (2); place-id order
    # still starts with cafe-a so the budget-1 assertion below is unchanged.
    assert summary.freshness_required == 3
    assert summary.freshness_completed == 1
    assert summary.freshness_remaining == 2
    assert freshness_provider.calls == ["cafe-a"]
    assert cache.freshness_payloads["cafe-a"].review_sort == "newest"
