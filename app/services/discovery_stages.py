from collections.abc import Callable
from dataclasses import asdict, dataclass

from app.adapters.base import (
    PagedPlaceDiscoveryProvider,
    ReviewFreshnessProvider,
)
from app.catalog import VenueCatalog
from app.data_collection_config import DataCollectionConfig
from app.discovery.search_cache import (
    CachedCandidate,
    CachedFreshnessPayload,
    DiscoverySearchCache,
    SearchPageRecord,
)
from app.discovery.selector import apply_hard_filters, deduplicate_candidates

Checkpoint = Callable[[DiscoverySearchCache], None]


@dataclass(frozen=True, slots=True)
class SearchStageSummary:
    requests_this_run: int
    total_search_requests: int
    search_completed: bool
    raw_candidates: int
    unique_new_candidates: int
    eligible_candidate_count: int
    minimum_candidate_pool: int
    completion_reason: str | None
    freshness_required: int | None
    query_status: tuple[dict[str, object], ...]


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
):
    existing_place_ids = {entry.place_id for entry in catalog.venues}
    new_candidates = tuple(
        candidate
        for candidate in cache.domain_candidates()
        if candidate.place_id not in existing_place_ids
    )
    unique_candidates = deduplicate_candidates(new_candidates)
    filtered = apply_hard_filters(unique_candidates, config=config.discovery)
    return unique_candidates, filtered


def complete_search_if_pool_ready(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
) -> bool:
    """Stop pagination once the configured viable candidate pool is available."""
    if cache.search_completed:
        if cache.completion_reason is None:
            cache.completion_reason = "pages_exhausted"
            return True
        return False

    _, filtered = _filtered_candidates(cache, config=config, catalog=catalog)
    needed = max(0, cache.target_count - len(catalog.venues))
    pool_target = max(needed, config.discovery.minimum_candidate_pool)
    if len(filtered.candidates) < pool_target:
        return False

    for query in cache.queries:
        query.completed = True
    cache.completion_reason = "minimum_candidate_pool"
    return True


def freshness_shortlist(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
):
    """Every locally-eligible candidate that still needs a freshness check.

    This must not be pre-narrowed to target_count: final selection (in
    build_discovery_result) scores candidates using the real freshness
    result, and can only let freshness change the outcome if candidates
    beyond target_count are still in play to be out-ranked by a fresher one.
    """
    _, filtered = _filtered_candidates(cache, config=config, catalog=catalog)
    return filtered.candidates


def search_stage_summary(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
    requests_this_run: int,
) -> SearchStageSummary:
    unique_candidates, filtered = _filtered_candidates(
        cache,
        config=config,
        catalog=catalog,
    )
    return SearchStageSummary(
        requests_this_run=requests_this_run,
        total_search_requests=cache.total_search_requests,
        search_completed=cache.search_completed,
        raw_candidates=len(cache.candidates),
        unique_new_candidates=len(unique_candidates),
        eligible_candidate_count=len(filtered.candidates),
        minimum_candidate_pool=max(
            max(0, cache.target_count - len(catalog.venues)),
            config.discovery.minimum_candidate_pool,
        ),
        completion_reason=cache.completion_reason,
        freshness_required=(
            len(freshness_shortlist(cache, config=config, catalog=catalog))
            if cache.search_completed
            else None
        ),
        query_status=tuple(
            {
                "category": query.category,
                "request_count": query.request_count,
                "completed": query.completed,
                "has_next_page": query.next_page_token is not None,
            }
            for query in cache.queries
        ),
    )


class DiscoverySearchStage:
    def __init__(self, provider: PagedPlaceDiscoveryProvider) -> None:
        self._provider = provider

    async def run(
        self,
        *,
        cache: DiscoverySearchCache,
        config: DataCollectionConfig,
        catalog: VenueCatalog,
        max_requests: int,
        checkpoint: Checkpoint,
    ) -> SearchStageSummary:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if complete_search_if_pool_ready(cache, config=config, catalog=catalog):
            checkpoint(cache)
        requests_made = 0
        for query in cache.queries:
            while not query.completed and requests_made < max_requests:
                request_page_token = query.next_page_token if query.started else None
                page = await self._provider.search_page(
                    category=query.category,
                    text_query=query.text_query,
                    included_type=query.included_type,
                    latitude=config.region.center.latitude,
                    longitude=config.region.center.longitude,
                    radius_meters=config.discovery.radius_meters,
                    page_size=config.discovery.page_size,
                    page_token=request_page_token,
                )
                used_tokens = {
                    record.request_page_token
                    for record in cache.pages
                    if record.category == query.category
                    and record.request_page_token is not None
                }
                if page.next_page_token and page.next_page_token in used_tokens:
                    raise RuntimeError("Text Search returned a repeated page token")
                query.started = True
                query.request_count += 1
                query.next_page_token = page.next_page_token
                query.completed = page.next_page_token is None
                cache.candidates.extend(
                    CachedCandidate.from_domain(candidate)
                    for candidate in page.candidates
                )
                cache.pages.append(
                    SearchPageRecord(
                        category=query.category,
                        request_page_token=request_page_token,
                        next_page_token=page.next_page_token,
                        fetched_at=page.fetched_at.isoformat(),
                        candidate_count=len(page.candidates),
                        raw_payload=page.raw_payload,
                    )
                )
                requests_made += 1
                complete_search_if_pool_ready(
                    cache,
                    config=config,
                    catalog=catalog,
                )
                checkpoint(cache)
            if requests_made >= max_requests:
                break

        return search_stage_summary(
            cache,
            config=config,
            catalog=catalog,
            requests_this_run=requests_made,
        )


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
    ) -> FreshnessStageSummary:
        if not cache.search_completed:
            raise ValueError("Search stage is not complete")
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        required = tuple(
            sorted(
                freshness_shortlist(cache, config=config, catalog=catalog),
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


def summary_dict(summary: SearchStageSummary | FreshnessStageSummary) -> dict:
    return asdict(summary)
