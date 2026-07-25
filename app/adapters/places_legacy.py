import asyncio
import hashlib
import json
import unicodedata
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

import httpx

from app.adapters.base import (
    PlaceFetchBundle,
    PlaceState,
    ProviderUnavailableError,
    RawPlacePayload,
    ReviewAppearanceData,
    ReviewData,
    ReviewFreshnessResult,
)

DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
RETRYABLE_PAYLOAD_STATUSES = {"OVER_QUERY_LIMIT", "UNKNOWN_ERROR"}


class PlacesApiError(RuntimeError):
    def __init__(self, message: str, *, status: str | None = None) -> None:
        super().__init__(message)
        self.status = status


class LegacyPlacesUnavailableError(PlacesApiError, ProviderUnavailableError):
    pass


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def make_review_key(place_id: str, review: dict[str, Any]) -> str:
    author_identity = review.get("author_url") or review.get("author_name") or ""
    components = (
        place_id,
        _normalize(str(author_identity)),
        str(review.get("time", "")),
        str(review.get("rating", "")),
        _normalize(str(review.get("text", ""))),
    )
    return hashlib.sha256("\x1f".join(components).encode()).hexdigest()


def hash_payload(payload: dict[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


class PlacesLegacyAdapter:
    provider_name = "places_api"

    def __init__(
        self,
        api_key: str,
        *,
        timeout_seconds: float = 15.0,
        max_retries: int = 2,
        review_sorts: tuple[str, ...] = ("newest", "most_relevant"),
        fields: tuple[str, ...] = (
            "name",
            "business_status",
            "rating",
            "user_ratings_total",
            "price_level",
            "reviews",
        ),
        reviews_no_translations: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_retries = max_retries
        self._review_sorts = review_sorts
        self._fields = ",".join(fields)
        self._reviews_no_translations = reviews_no_translations
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch_place(
        self,
        place_id: str,
        *,
        existing_payloads: tuple[RawPlacePayload, ...] = (),
    ) -> PlaceFetchBundle:
        reusable = {
            payload.review_sort: payload
            for payload in existing_payloads
            if payload.review_sort in self._review_sorts
            and (payload.body.get("result") or {}).get("name")
        }
        missing_sorts = tuple(
            review_sort
            for review_sort in self._review_sorts
            if review_sort not in reusable
        )
        fetched = tuple(
            await asyncio.gather(
                *(
                    self._details_request(
                        place_id,
                        review_sort=review_sort,
                        fields=self._fields,
                    )
                    for review_sort in missing_sorts
                )
            )
        )
        by_sort = {
            payload.review_sort: payload for payload in (*reusable.values(), *fetched)
        }
        payloads = tuple(by_sort[review_sort] for review_sort in self._review_sorts)
        state_payload = next(
            (
                payload
                for payload in payloads
                if (payload.body.get("result") or {}).get("name")
            ),
            None,
        )
        if state_payload is None:
            raise PlacesApiError("Place Details payloads contain no venue state")
        state = self._parse_state(place_id, state_payload.body)
        reviews = self._parse_reviews(place_id, payloads)
        return PlaceFetchBundle(state=state, payloads=payloads, reviews=reviews)

    async def fetch_review_freshness(self, place_id: str) -> ReviewFreshnessResult:
        payload = await self._details_request(
            place_id,
            review_sort="newest",
            fields="reviews",
        )
        reviews = (payload.body.get("result") or {}).get("reviews") or []
        timestamps = [int(review["time"]) for review in reviews if review.get("time")]
        latest = datetime.fromtimestamp(max(timestamps), tz=UTC) if timestamps else None
        return ReviewFreshnessResult(latest_review_at=latest, payload=payload)

    async def _details_request(
        self,
        place_id: str,
        *,
        review_sort: str,
        fields: str,
    ) -> RawPlacePayload:
        request_variant = f"details_{review_sort}"
        body, fetched_at = await self._request_json(
            DETAILS_URL,
            {
                "place_id": place_id,
                "fields": fields,
                "language": "tr",
                "reviews_no_translations": str(self._reviews_no_translations).lower(),
                "reviews_sort": review_sort,
            },
        )
        return RawPlacePayload(
            request_variant=request_variant,
            review_sort=review_sort,
            fetched_at=fetched_at,
            body=body,
            payload_hash=hash_payload(body),
        )

    async def _request_json(
        self,
        url: str,
        params: dict[str, str],
    ) -> tuple[dict[str, Any], datetime]:
        request_params = {**params, "key": self._api_key}
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.get(url, params=request_params)
                fetched_at = datetime.now(UTC)
                response.raise_for_status()
                payload = response.json()
                status = payload.get("status")
                if status == "OK":
                    return payload, fetched_at
                if status in RETRYABLE_PAYLOAD_STATUSES and attempt < self._max_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                message = payload.get("error_message") or f"Places API status: {status}"
                if status == "REQUEST_DENIED":
                    raise LegacyPlacesUnavailableError(message, status=status)
                raise PlacesApiError(message, status=status)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                retryable = isinstance(exc, httpx.TransportError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )
                if retryable and attempt < self._max_retries:
                    await asyncio.sleep(0.25 * (2**attempt))
                    continue
                if isinstance(
                    exc, httpx.HTTPStatusError
                ) and exc.response.status_code in {
                    404,
                    410,
                }:
                    raise LegacyPlacesUnavailableError(
                        f"Places API Legacy endpoint is unavailable: {exc}"
                    ) from exc
                raise PlacesApiError(f"Places API request failed: {exc}") from exc

        raise PlacesApiError(f"Places API request failed: {last_error}")

    @staticmethod
    def _parse_state(place_id: str, payload: dict[str, Any]) -> PlaceState:
        result = payload.get("result") or {}
        returned_place_id = str(result.get("place_id") or place_id)
        if returned_place_id != place_id:
            raise PlacesApiError("Place Details returned a different place_id")
        name = result.get("name")
        if not name:
            raise PlacesApiError("Place Details response has no venue name")
        return PlaceState(
            place_id=place_id,
            name=str(name),
            rating=result.get("rating"),
            user_ratings_total=result.get("user_ratings_total"),
            price_level=result.get("price_level"),
            business_status=result.get("business_status"),
        )

    @staticmethod
    def _parse_reviews(
        place_id: str,
        payloads: tuple[RawPlacePayload, ...],
    ) -> tuple[ReviewData, ...]:
        raw_by_key: dict[str, dict[str, Any]] = {}
        appearances: dict[str, list[ReviewAppearanceData]] = defaultdict(list)

        for payload in payloads:
            reviews = (payload.body.get("result") or {}).get("reviews") or []
            for rank, review in enumerate(reviews, start=1):
                key = make_review_key(place_id, review)
                raw_by_key.setdefault(key, review)
                appearances[key].append(
                    ReviewAppearanceData(
                        request_variant=payload.request_variant,
                        review_sort=payload.review_sort,
                        rank=rank,
                    )
                )

        parsed: list[ReviewData] = []
        for key, raw_review in raw_by_key.items():
            published_at = datetime.fromtimestamp(int(raw_review["time"]), tz=UTC)
            parsed.append(
                ReviewData(
                    provider_review_id=raw_review.get("review_id"),
                    dedup_key=key,
                    author_name=str(raw_review.get("author_name") or "A Google user"),
                    author_url=raw_review.get("author_url"),
                    published_at=published_at,
                    rating=int(raw_review["rating"]),
                    text=str(raw_review.get("text") or ""),
                    language=raw_review.get("language"),
                    original_language=raw_review.get("original_language"),
                    translated=raw_review.get("translated"),
                    raw_review=raw_review,
                    appearances=tuple(appearances[key]),
                )
            )

        return tuple(parsed)
