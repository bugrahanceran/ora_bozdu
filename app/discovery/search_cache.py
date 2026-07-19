import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.adapters.base import DiscoveryCandidate, RawPlacePayload
from app.catalog import VenueCatalog
from app.data_collection_config import DataCollectionConfig


class CachedCandidate(BaseModel):
    place_id: str
    display_name: str
    category: str
    business_status: str | None
    user_ratings_total: int
    primary_type: str | None

    @classmethod
    def from_domain(cls, candidate: DiscoveryCandidate) -> "CachedCandidate":
        return cls(
            place_id=candidate.place_id,
            display_name=candidate.display_name,
            category=candidate.category,
            business_status=candidate.business_status,
            user_ratings_total=candidate.user_ratings_total,
            primary_type=candidate.primary_type,
        )

    def to_domain(self) -> DiscoveryCandidate:
        return DiscoveryCandidate(**self.model_dump())


class SearchQueryState(BaseModel):
    category: str
    text_query: str
    included_type: str
    next_page_token: str | None = None
    started: bool = False
    completed: bool = False
    request_count: int = 0


class SearchPageRecord(BaseModel):
    category: str
    request_page_token: str | None
    next_page_token: str | None
    fetched_at: str
    candidate_count: int
    raw_payload: dict[str, Any]


class CachedFreshnessPayload(BaseModel):
    request_variant: str
    review_sort: str
    fetched_at: datetime
    raw_payload: dict[str, Any]
    payload_hash: str

    @classmethod
    def from_domain(cls, payload: RawPlacePayload) -> "CachedFreshnessPayload":
        return cls(
            request_variant=payload.request_variant,
            review_sort=payload.review_sort,
            fetched_at=payload.fetched_at,
            raw_payload=payload.body,
            payload_hash=payload.payload_hash,
        )

    def to_domain(self) -> RawPlacePayload:
        return RawPlacePayload(
            request_variant=self.request_variant,
            review_sort=self.review_sort,
            fetched_at=self.fetched_at,
            body=self.raw_payload,
            payload_hash=self.payload_hash,
        )


class DiscoverySearchCache(BaseModel):
    version: str = "discovery-search.v1"
    collection_config_hash: str
    catalog_hash: str
    region_slug: str
    target_count: int
    as_of_date: date
    queries: list[SearchQueryState]
    candidates: list[CachedCandidate] = Field(default_factory=list)
    pages: list[SearchPageRecord] = Field(default_factory=list)
    freshness_results: dict[str, str | None] = Field(default_factory=dict)
    freshness_payloads: dict[str, CachedFreshnessPayload] = Field(default_factory=dict)
    completion_reason: str | None = None

    @property
    def search_completed(self) -> bool:
        return all(query.completed for query in self.queries)

    @property
    def total_search_requests(self) -> int:
        return sum(query.request_count for query in self.queries)

    def domain_candidates(self) -> tuple[DiscoveryCandidate, ...]:
        return tuple(candidate.to_domain() for candidate in self.candidates)


def create_search_cache(
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
    collection_config_hash: str,
    catalog_hash: str,
    target_count: int,
    as_of_date: date,
) -> DiscoverySearchCache:
    return DiscoverySearchCache(
        collection_config_hash=collection_config_hash,
        catalog_hash=catalog_hash,
        region_slug=config.region.slug,
        target_count=target_count,
        as_of_date=as_of_date,
        queries=[
            SearchQueryState(
                category=query.category,
                text_query=query.text_query,
                included_type=query.included_type,
            )
            for query in config.discovery.queries
        ],
    )


def load_search_cache(path: Path) -> DiscoverySearchCache:
    return DiscoverySearchCache.model_validate_json(path.read_text(encoding="utf-8"))


def write_search_cache(path: Path, cache: DiscoverySearchCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
