import json
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.adapters.base import DiscoveryCandidate, RawPlacePayload
from app.data_collection_config import DataCollectionConfig
from app.discovery.grid import GridCellSpec, build_grid, chunk_types


class CachedCandidate(BaseModel):
    place_id: str
    display_name: str
    category: str
    business_status: str | None
    user_ratings_total: int
    primary_type: str | None
    latitude: float
    longitude: float

    @classmethod
    def from_domain(cls, candidate: DiscoveryCandidate) -> "CachedCandidate":
        return cls(
            place_id=candidate.place_id,
            display_name=candidate.display_name,
            category=candidate.category,
            business_status=candidate.business_status,
            user_ratings_total=candidate.user_ratings_total,
            primary_type=candidate.primary_type,
            latitude=candidate.latitude,
            longitude=candidate.longitude,
        )

    def to_domain(self) -> DiscoveryCandidate:
        return DiscoveryCandidate(**self.model_dump())


class GridCellState(BaseModel):
    cell_id: str
    center_latitude: float
    center_longitude: float
    radius_meters: float
    included_types: tuple[str, ...]
    depth: int = 0
    parent_cell_id: str | None = None
    status: Literal["pending", "searched", "split"] = "pending"
    result_count: int | None = None
    hit_result_cap: bool = False
    searched_at: datetime | None = None

    @classmethod
    def from_spec(
        cls,
        spec: GridCellSpec,
        *,
        included_types: tuple[str, ...],
    ) -> "GridCellState":
        return cls(
            cell_id=spec.cell_id,
            center_latitude=spec.center_latitude,
            center_longitude=spec.center_longitude,
            radius_meters=spec.radius_meters,
            included_types=included_types,
        )


class CellSearchRecord(BaseModel):
    cell_id: str
    fetched_at: datetime
    candidate_count: int
    hit_result_cap: bool
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
    version: str = "discovery-search.v2"
    collection_config_hash: str
    catalog_hash: str
    region_slug: str
    as_of_date: date
    cells: list[GridCellState]
    candidates: list[CachedCandidate] = Field(default_factory=list)
    cell_search_records: list[CellSearchRecord] = Field(default_factory=list)
    freshness_results: dict[str, str | None] = Field(default_factory=dict)
    freshness_payloads: dict[str, CachedFreshnessPayload] = Field(default_factory=dict)

    @property
    def search_completed(self) -> bool:
        return all(cell.status != "pending" for cell in self.cells)

    @property
    def total_search_requests(self) -> int:
        return sum(1 for cell in self.cells if cell.status != "pending")

    @property
    def cells_flagged_for_review(self) -> tuple[GridCellState, ...]:
        """Terminal cells that hit the result cap and were never subdivided.

        Historical caches (from when a single level of adaptive splitting
        existed) may still contain `status="split"` parents that hit the cap
        but were superseded by their children -- those aren't flagged, only
        cells whose (possibly truncated) result was accepted as final.
        """
        return tuple(
            cell
            for cell in self.cells
            if cell.status == "searched" and cell.hit_result_cap
        )

    def domain_candidates(self) -> tuple[DiscoveryCandidate, ...]:
        return tuple(candidate.to_domain() for candidate in self.candidates)


def create_search_cache(
    *,
    config: DataCollectionConfig,
    collection_config_hash: str,
    catalog_hash: str,
    as_of_date: date,
) -> DiscoverySearchCache:
    base_cells = build_grid(
        center_latitude=config.region.center.latitude,
        center_longitude=config.region.center.longitude,
        region_radius_meters=config.discovery.radius_meters,
        cell_radius_meters=config.discovery.cell_radius_meters,
    )
    type_batches = chunk_types(config.discovery.included_types)
    cells = [
        GridCellState.from_spec(
            replace(cell, cell_id=f"{cell.cell_id}.batch{batch_index}"),
            included_types=batch,
        )
        for cell in base_cells
        for batch_index, batch in enumerate(type_batches)
    ]
    return DiscoverySearchCache(
        collection_config_hash=collection_config_hash,
        catalog_hash=catalog_hash,
        region_slug=config.region.slug,
        as_of_date=as_of_date,
        cells=cells,
    )


def load_search_cache(path: Path) -> DiscoverySearchCache:
    return DiscoverySearchCache.model_validate_json(path.read_text(encoding="utf-8"))


def write_search_cache(path: Path, cache: DiscoverySearchCache) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
