from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


class ProviderUnavailableError(RuntimeError):
    """Raised when a required provider endpoint cannot be used."""


@dataclass(frozen=True, slots=True)
class PlaceState:
    place_id: str
    name: str
    rating: float | None
    user_ratings_total: int | None
    price_level: int | None
    business_status: str | None


@dataclass(frozen=True, slots=True)
class RawPlacePayload:
    request_variant: str
    review_sort: str
    fetched_at: datetime
    body: dict[str, Any]
    payload_hash: str


@dataclass(frozen=True, slots=True)
class ReviewAppearanceData:
    request_variant: str
    review_sort: str
    rank: int


@dataclass(frozen=True, slots=True)
class ReviewData:
    provider_review_id: str | None
    dedup_key: str
    author_name: str
    author_url: str | None
    published_at: datetime
    rating: int
    text: str
    language: str | None
    original_language: str | None
    translated: bool | None
    raw_review: dict[str, Any]
    appearances: tuple[ReviewAppearanceData, ...]


@dataclass(frozen=True, slots=True)
class PlaceFetchBundle:
    state: PlaceState
    payloads: tuple[RawPlacePayload, ...]
    reviews: tuple[ReviewData, ...]


@dataclass(frozen=True, slots=True)
class ReviewFreshnessResult:
    latest_review_at: datetime | None
    payload: RawPlacePayload


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    place_id: str
    display_name: str
    category: str
    business_status: str | None
    user_ratings_total: int
    primary_type: str | None
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class NearbySearchCellResult:
    candidates: tuple[DiscoveryCandidate, ...]
    fetched_at: datetime
    raw_payload: dict[str, Any]
    hit_result_cap: bool


class NearbySearchProvider(Protocol):
    provider_name: str

    async def search_cell(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float,
        included_types: tuple[str, ...],
        excluded_types: tuple[str, ...],
        rank_preference: str,
        max_result_count: int,
    ) -> NearbySearchCellResult: ...

    async def aclose(self) -> None: ...


class ReviewFreshnessProvider(Protocol):
    provider_name: str

    async def fetch_review_freshness(self, place_id: str) -> ReviewFreshnessResult: ...

    async def aclose(self) -> None: ...


class PlaceDataProvider(Protocol):
    provider_name: str

    async def fetch_place(
        self,
        place_id: str,
        *,
        existing_payloads: tuple[RawPlacePayload, ...] = (),
    ) -> PlaceFetchBundle: ...

    async def aclose(self) -> None: ...
