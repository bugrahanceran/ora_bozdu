import json

import httpx
import pytest

from app.adapters.places_new import (
    TEXT_SEARCH_FIELD_MASK,
    PlacesNewAccessError,
    PlacesNewTextSearchAdapter,
)


@pytest.mark.asyncio
async def test_text_search_paginates_with_minimal_field_mask() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        bodies.append(body)
        assert request.headers["X-Goog-FieldMask"] == TEXT_SEARCH_FIELD_MASK
        assert "reviews" not in request.headers["X-Goog-FieldMask"]
        if "pageToken" not in body:
            return httpx.Response(
                200,
                json={
                    "places": [
                        {
                            "id": "place-b",
                            "displayName": {"text": "Beta Cafe"},
                            "businessStatus": "OPERATIONAL",
                            "userRatingCount": 150,
                            "primaryType": "cafe",
                            "location": {"latitude": 39.98, "longitude": 32.64},
                        },
                        {
                            "id": "outside-radius",
                            "displayName": {"text": "Outside Cafe"},
                            "businessStatus": "OPERATIONAL",
                            "userRatingCount": 900,
                            "primaryType": "cafe",
                            "location": {"latitude": 39.997, "longitude": 32.655},
                        },
                    ],
                    "nextPageToken": "next-token",
                },
            )
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
    adapter = PlacesNewTextSearchAdapter("test-key", client=client)
    try:
        candidates = await adapter.search(
            category="cafe",
            text_query="cafe",
            included_type="cafe",
            latitude=39.979,
            longitude=32.636,
            radius_meters=2000,
            page_size=20,
        )
    finally:
        await client.aclose()

    assert [candidate.place_id for candidate in candidates] == ["place-b", "place-a"]
    assert bodies[1]["pageToken"] == "next-token"
    rectangle = bodies[0]["locationRestriction"]["rectangle"]
    assert rectangle["low"]["latitude"] < 39.979
    assert rectangle["low"]["longitude"] < 32.636
    assert rectangle["high"]["latitude"] > 39.979
    assert rectangle["high"]["longitude"] > 32.636
    assert "locationBias" not in bodies[0]
    assert bodies[0]["strictTypeFiltering"] is True


@pytest.mark.asyncio
async def test_general_query_omits_included_type_and_infers_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert "includedType" not in body
        assert "strictTypeFiltering" not in body
        return httpx.Response(
            200,
            json={
                "places": [
                    {
                        "id": "place-cafe",
                        "displayName": {"text": "Mixed Cafe"},
                        "businessStatus": "OPERATIONAL",
                        "userRatingCount": 120,
                        "primaryType": "cafe",
                        "location": {"latitude": 39.979, "longitude": 32.636},
                    },
                    {
                        "id": "place-restaurant",
                        "displayName": {"text": "Mixed Restaurant"},
                        "businessStatus": "OPERATIONAL",
                        "userRatingCount": 300,
                        "primaryType": "restaurant",
                        "location": {"latitude": 39.979, "longitude": 32.636},
                    },
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = PlacesNewTextSearchAdapter("test-key", client=client)
    try:
        candidates = await adapter.search(
            category="general",
            text_query="restoran ve kafe",
            included_type=None,
            latitude=39.979,
            longitude=32.636,
            radius_meters=2000,
            page_size=20,
        )
    finally:
        await client.aclose()

    by_id = {candidate.place_id: candidate for candidate in candidates}
    assert by_id["place-cafe"].category == "cafe"
    assert by_id["place-restaurant"].category == "restaurant"


@pytest.mark.asyncio
async def test_text_search_surfaces_google_access_error_details() -> None:
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
    adapter = PlacesNewTextSearchAdapter("test-key", client=client, max_retries=0)
    try:
        with pytest.raises(PlacesNewAccessError, match="PERMISSION_DENIED"):
            await adapter.search_page(
                category="cafe",
                text_query="cafe",
                included_type="cafe",
                latitude=39.979,
                longitude=32.636,
                radius_meters=2000,
                page_size=20,
                page_token=None,
            )
    finally:
        await client.aclose()
