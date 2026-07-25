import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import DiscoveryCandidate, NearbySearchCellResult

NEARBY_SEARCH_URL = "https://places.googleapis.com/v1/places:searchNearby"
NEARBY_SEARCH_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.businessStatus",
        "places.userRatingCount",
        "places.primaryType",
        "places.location",
    )
)


class PlacesNewApiError(RuntimeError):
    pass


class PlacesNewAccessError(PlacesNewApiError):
    pass


class PlacesNearbySearchAdapter:
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
    ) -> NearbySearchCellResult:
        body: dict[str, Any] = {
            "languageCode": "tr",
            "regionCode": "TR",
            "maxResultCount": max_result_count,
            "rankPreference": rank_preference,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": radius_meters,
                }
            },
            "includedTypes": list(included_types),
        }
        if excluded_types:
            body["excludedTypes"] = list(excluded_types)
        payload = await self._request_json(body)
        candidates = self._parse_candidates(payload)
        return NearbySearchCellResult(
            candidates=candidates,
            fetched_at=datetime.now(UTC),
            raw_payload=payload,
            hit_result_cap=len(candidates) >= max_result_count,
        )

    async def _request_json(self, body: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": NEARBY_SEARCH_FIELD_MASK,
        }
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    NEARBY_SEARCH_URL,
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
                        "Nearby Search request failed with "
                        f"HTTP {exc.response.status_code}: {details}"
                    ) from exc
                raise PlacesNewApiError(f"Nearby Search request failed: {exc}") from exc
        raise PlacesNewApiError(f"Nearby Search request failed: {last_error}")

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
    def _parse_candidates(
        payload: dict[str, Any],
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
            primary_type = place.get("primaryType")
            parsed.append(
                DiscoveryCandidate(
                    place_id=str(place_id),
                    display_name=str(display_name),
                    category=str(primary_type) if primary_type else "unknown",
                    business_status=place.get("businessStatus"),
                    user_ratings_total=int(place.get("userRatingCount") or 0),
                    primary_type=primary_type,
                    latitude=float(place_latitude),
                    longitude=float(place_longitude),
                )
            )
        return tuple(parsed)
