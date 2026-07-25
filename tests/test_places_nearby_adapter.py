import json

import httpx
import pytest

from app.adapters.places_nearby import (
    NEARBY_SEARCH_FIELD_MASK,
    PlacesNearbySearchAdapter,
    PlacesNewAccessError,
)


@pytest.mark.asyncio
async def test_search_cell_sends_circle_restriction_and_minimal_field_mask() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        assert request.headers["X-Goog-FieldMask"] == NEARBY_SEARCH_FIELD_MASK
        assert "reviews" not in request.headers["X-Goog-FieldMask"]
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "place-a",
                        "displayName": {"text": "Alpha Cafe"},
                        "businessStatus": "OPERATIONAL",
                        "userRatingCount": 250,
                        "primaryType": "cafe",
                        "location": {"latitude": 39.978, "longitude": 32.635},
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesNearbySearchAdapter("test-key", client=client)
    try:
        result = await adapter.search_cell(
            latitude=39.979,
            longitude=32.636,
            radius_meters=500,
            included_types=("cafe", "restaurant"),
            excluded_types=(),
            rank_preference="POPULARITY",
            max_result_count=20,
        )
    finally:
        await client.aclose()

    assert [candidate.place_id for candidate in result.candidates] == ["place-a"]
    assert result.candidates[0].latitude == 39.978
    assert result.candidates[0].longitude == 32.635
    assert result.hit_result_cap is False
    body = bodies[0]
    assert body["locationRestriction"]["circle"]["center"] == {
        "latitude": 39.979,
        "longitude": 32.636,
    }
    assert body["locationRestriction"]["circle"]["radius"] == 500
    assert body["includedTypes"] == ["cafe", "restaurant"]
    assert "excludedTypes" not in body
    assert body["rankPreference"] == "POPULARITY"
    assert body["maxResultCount"] == 20
    assert "locationBias" not in body


@pytest.mark.asyncio
async def test_search_cell_sends_excluded_types_when_present() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["excludedTypes"] == ["fast_food_restaurant"]
        return httpx.Response(200, json={"places": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesNearbySearchAdapter("test-key", client=client)
    try:
        await adapter.search_cell(
            latitude=39.979,
            longitude=32.636,
            radius_meters=500,
            included_types=("restaurant",),
            excluded_types=("fast_food_restaurant",),
            rank_preference="POPULARITY",
            max_result_count=20,
        )
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_search_cell_detects_result_cap_hit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": f"place-{index}",
                        "displayName": {"text": f"Place {index}"},
                        "businessStatus": "OPERATIONAL",
                        "userRatingCount": 100,
                        "primaryType": "cafe",
                        "location": {"latitude": 39.979, "longitude": 32.636},
                    }
                    for index in range(3)
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesNearbySearchAdapter("test-key", client=client)
    try:
        result = await adapter.search_cell(
            latitude=39.979,
            longitude=32.636,
            radius_meters=500,
            included_types=("cafe",),
            excluded_types=(),
            rank_preference="POPULARITY",
            max_result_count=3,
        )
    finally:
        await client.aclose()

    assert len(result.candidates) == 3
    assert result.hit_result_cap is True


@pytest.mark.asyncio
async def test_nearby_search_surfaces_google_access_error_details() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            request=request,
            json={
                "error": {
                    "status": "PERMISSION_DENIED",
                    "message": "Places API (New) is not enabled",
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesNearbySearchAdapter("test-key", client=client, max_retries=0)
    try:
        with pytest.raises(PlacesNewAccessError, match="PERMISSION_DENIED"):
            await adapter.search_cell(
                latitude=39.979,
                longitude=32.636,
                radius_meters=500,
                included_types=("cafe",),
                excluded_types=(),
                rank_preference="POPULARITY",
                max_result_count=20,
            )
    finally:
        await client.aclose()
