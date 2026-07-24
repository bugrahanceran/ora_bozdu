import asyncio
import math
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import DiscoveryCandidate, DiscoveryPage

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TEXT_SEARCH_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.businessStatus",
        "places.userRatingCount",
        "places.primaryType",
        "places.location",
        "nextPageToken",
    )
)

EARTH_RADIUS_METERS = 6_371_008.8


class PlacesNewApiError(RuntimeError):
    pass


class PlacesNewAccessError(PlacesNewApiError):
    pass


class PlacesNewTextSearchAdapter:
    provider_name = "places_api_new"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def search(
        self,
        *,
        category: str,
        text_query: str,
        included_type: str | None,
        latitude: float,
        longitude: float,
        radius_meters: float,
        page_size: int,
    ) -> tuple[DiscoveryCandidate, ...]:
        candidates: list[DiscoveryCandidate] = []
        page_token: str | None = None
        seen_tokens: set[str] = set()

        while True:
            page = await self.search_page(
                category=category,
                text_query=text_query,
                included_type=included_type,
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius_meters,
                page_size=page_size,
                page_token=page_token,
            )
            candidates.extend(page.candidates)
            page_token = page.next_page_token
            if not page_token:
                break
            if page_token in seen_tokens:
                raise PlacesNewApiError("Text Search returned a repeated page token")
            seen_tokens.add(page_token)

        return tuple(candidates)

    async def search_page(
        self,
        *,
        category: str,
        text_query: str,
        included_type: str | None,
        latitude: float,
        longitude: float,
        radius_meters: float,
        page_size: int,
        page_token: str | None,
    ) -> DiscoveryPage:
        body: dict[str, Any] = {
            "textQuery": text_query,
            "languageCode": "tr",
            "regionCode": "TR",
            "pageSize": page_size,
            "locationRestriction": {
                "rectangle": self._bounding_rectangle(
                    latitude=latitude,
                    longitude=longitude,
                    radius_meters=radius_meters,
                )
            },
        }
        if included_type:
            body["includedType"] = included_type
            body["strictTypeFiltering"] = True
        if page_token:
            body["pageToken"] = page_token
        payload = await self._request_json(body)
        return DiscoveryPage(
            candidates=self._parse_candidates(
                payload,
                category,
                latitude=latitude,
                longitude=longitude,
                radius_meters=radius_meters,
            ),
            next_page_token=payload.get("nextPageToken"),
            fetched_at=datetime.now(UTC),
            raw_payload=payload,
        )

    async def _request_json(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": TEXT_SEARCH_FIELD_MASK,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    TEXT_SEARCH_URL,
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                return response.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = isinstance(exc, httpx.TransportError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if retryable and attempt < self._max_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if isinstance(exc, httpx.HTTPStatusError):
                    details = self._response_error_details(exc.response)
                    error_type = (
                        PlacesNewAccessError
                        if exc.response.status_code in {401, 403}
                        else PlacesNewApiError
                    )
                    raise error_type(
                        "Text Search request failed with "
                        f"HTTP {exc.response.status_code}: {details}"
                    ) from exc
                raise PlacesNewApiError(f"Text Search request failed: {exc}") from exc
        raise PlacesNewApiError(f"Text Search request failed: {last_error}")

    @staticmethod
    def _response_error_details(response: httpx.Response) -> str:
        try:
            error = response.json().get("error") or {}
        except ValueError:
            return response.text[:500] or "No response body"
        status = error.get("status")
        message = error.get("message")
        return (
            ": ".join(str(value) for value in (status, message) if value)
            or str(error)[:500]
        )

    @staticmethod
    def _bounding_rectangle(
        *, latitude: float, longitude: float, radius_meters: float
    ) -> dict[str, dict[str, float]]:
        """Return a viewport enclosing the configured spherical search circle."""
        angular_radius = radius_meters / EARTH_RADIUS_METERS
        latitude_radians = math.radians(latitude)
        minimum_latitude = max(-math.pi / 2, latitude_radians - angular_radius)
        maximum_latitude = min(math.pi / 2, latitude_radians + angular_radius)

        if minimum_latitude > -math.pi / 2 and maximum_latitude < math.pi / 2:
            longitude_delta = math.asin(
                min(1.0, math.sin(angular_radius) / math.cos(latitude_radians))
            )
            minimum_longitude = PlacesNewTextSearchAdapter._normalize_longitude(
                longitude - math.degrees(longitude_delta)
            )
            maximum_longitude = PlacesNewTextSearchAdapter._normalize_longitude(
                longitude + math.degrees(longitude_delta)
            )
        else:
            minimum_longitude = -180.0
            maximum_longitude = 180.0

        return {
            "low": {
                "latitude": math.degrees(minimum_latitude),
                "longitude": minimum_longitude,
            },
            "high": {
                "latitude": math.degrees(maximum_latitude),
                "longitude": maximum_longitude,
            },
        }

    @staticmethod
    def _normalize_longitude(longitude: float) -> float:
        return ((longitude + 180.0) % 360.0) - 180.0

    @staticmethod
    def _distance_meters(
        *,
        origin_latitude: float,
        origin_longitude: float,
        destination_latitude: float,
        destination_longitude: float,
    ) -> float:
        origin_latitude_radians = math.radians(origin_latitude)
        destination_latitude_radians = math.radians(destination_latitude)
        latitude_delta = destination_latitude_radians - origin_latitude_radians
        longitude_delta = math.radians(destination_longitude - origin_longitude)
        haversine = math.sin(latitude_delta / 2) ** 2 + (
            math.cos(origin_latitude_radians)
            * math.cos(destination_latitude_radians)
            * math.sin(longitude_delta / 2) ** 2
        )
        return 2 * EARTH_RADIUS_METERS * math.asin(min(1.0, math.sqrt(haversine)))

    @staticmethod
    def _parse_candidates(
        payload: dict[str, Any],
        category: str,
        *,
        latitude: float,
        longitude: float,
        radius_meters: float,
    ) -> tuple[DiscoveryCandidate, ...]:
        parsed: list[DiscoveryCandidate] = []
        for place in payload.get("places") or ():
            place_id = place.get("id")
            display_name = (place.get("displayName") or {}).get("text")
            location = place.get("location") or {}
            place_latitude = location.get("latitude")
            place_longitude = location.get("longitude")
            if (
                not place_id
                or not display_name
                or place_latitude is None
                or place_longitude is None
            ):
                continue
            if (
                PlacesNewTextSearchAdapter._distance_meters(
                    origin_latitude=latitude,
                    origin_longitude=longitude,
                    destination_latitude=float(place_latitude),
                    destination_longitude=float(place_longitude),
                )
                > radius_meters
            ):
                continue
            primary_type = place.get("primaryType")
            parsed.append(
                DiscoveryCandidate(
                    place_id=str(place_id),
                    display_name=str(display_name),
                    category=str(primary_type) if primary_type else category,
                    business_status=place.get("businessStatus"),
                    user_ratings_total=int(place.get("userRatingCount") or 0),
                    primary_type=primary_type,
                )
            )
        return tuple(parsed)
