import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.adapters.base import RawPlacePayload
from app.adapters.places_legacy import PlacesLegacyAdapter, hash_payload

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


@pytest.mark.asyncio
async def test_fetches_both_sorts_and_deduplicates_reviews() -> None:
    primary = _load("place_details_most_relevant.json")
    newest = _load("place_details_newest.json")
    seen_sorts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        review_sort = request.url.params["reviews_sort"]
        seen_sorts.append(review_sort)
        payload = primary if review_sort == "most_relevant" else newest
        assert request.url.params["reviews_no_translations"] == "true"
        assert set(request.url.params["fields"].split(",")) == {
            "name",
            "business_status",
            "rating",
            "user_ratings_total",
            "price_level",
            "reviews",
        }
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesLegacyAdapter("test-key", client=client)
    try:
        bundle = await adapter.fetch_place("place-1")
    finally:
        await client.aclose()

    assert sorted(seen_sorts) == ["most_relevant", "newest"]
    assert bundle.state.name == "Fixture Cafe"
    assert bundle.state.rating == 4.4
    assert len(bundle.payloads) == 2
    assert len(bundle.reviews) == 3
    ayse = next(review for review in bundle.reviews if review.author_name == "Ayşe")
    assert {appearance.review_sort for appearance in ayse.appearances} == {
        "most_relevant",
        "newest",
    }


@pytest.mark.asyncio
async def test_fetches_newest_review_date_for_discovery_freshness() -> None:
    newest = _load("place_details_newest.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["reviews_sort"] == "newest"
        assert request.url.params["fields"] == "reviews"
        return httpx.Response(200, json=newest)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesLegacyAdapter("test-key", client=client)
    try:
        result = await adapter.fetch_review_freshness("place-1")
    finally:
        await client.aclose()

    expected = max(review["time"] for review in newest["result"]["reviews"])
    assert result.latest_review_at is not None
    assert int(result.latest_review_at.timestamp()) == expected
    assert result.payload.body == newest
    assert result.payload.review_sort == "newest"


@pytest.mark.asyncio
async def test_fetch_reuses_cached_newest_payload() -> None:
    primary = _load("place_details_most_relevant.json")
    newest = _load("place_details_newest.json")
    seen_sorts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        review_sort = request.url.params["reviews_sort"]
        seen_sorts.append(review_sort)
        assert review_sort == "most_relevant"
        return httpx.Response(200, json=primary)

    cached_newest = RawPlacePayload(
        request_variant="details_newest",
        review_sort="newest",
        fetched_at=datetime(2026, 7, 19, tzinfo=UTC),
        body=newest,
        payload_hash=hash_payload(newest),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesLegacyAdapter("test-key", client=client)
    try:
        bundle = await adapter.fetch_place(
            "place-1", existing_payloads=(cached_newest,)
        )
    finally:
        await client.aclose()

    assert seen_sorts == ["most_relevant"]
    assert {payload.review_sort for payload in bundle.payloads} == {
        "newest",
        "most_relevant",
    }
    assert bundle.state.name == "Fixture Cafe"


@pytest.mark.asyncio
async def test_fetch_does_not_reuse_a_state_less_freshness_seed() -> None:
    # Discovery's freshness stage requests `fields=reviews` only, so its
    # cached "newest" payload has no `name` -- reusing it as-is would leave
    # fetch_place with no payload to derive PlaceState from. A single-sort
    # (newest-only) config must fall through to a fresh, full-field request
    # instead of trusting this state-less seed.
    full_newest = _load("place_details_newest.json")
    seen_sorts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        review_sort = request.url.params["reviews_sort"]
        seen_sorts.append(review_sort)
        assert review_sort == "newest"
        assert set(request.url.params["fields"].split(",")) == {
            "name",
            "business_status",
            "rating",
            "user_ratings_total",
            "price_level",
            "reviews",
        }
        return httpx.Response(200, json=full_newest)

    state_less_seed = RawPlacePayload(
        request_variant="details_newest",
        review_sort="newest",
        fetched_at=datetime(2026, 7, 19, tzinfo=UTC),
        body={"status": "OK", "result": {"reviews": []}},
        payload_hash=hash_payload({"status": "OK", "result": {"reviews": []}}),
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesLegacyAdapter("test-key", client=client, review_sorts=("newest",))
    try:
        bundle = await adapter.fetch_place(
            "place-1", existing_payloads=(state_less_seed,)
        )
    finally:
        await client.aclose()

    assert seen_sorts == ["newest"]
    assert bundle.state.name == "Fixture Cafe"
    assert bundle.state.rating == 4.4
