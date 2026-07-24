from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.adapters.base import (
    DiscoveryCandidate,
    RawPlacePayload,
    ReviewFreshnessResult,
)
from app.catalog import VenueCatalog, VenueCatalogEntry
from app.data_collection_config import load_data_collection_config
from app.services.discovery_service import DiscoveryService


class FakeDiscoveryProvider:
    provider_name = "places_api_new"

    async def search(self, **kwargs) -> tuple[DiscoveryCandidate, ...]:
        # A single unified query still returns a mix of primary types.
        return (
            DiscoveryCandidate(
                place_id="cafe-place",
                display_name="Fixture Cafe",
                category="cafe",
                business_status="OPERATIONAL",
                user_ratings_total=500,
                primary_type="cafe",
            ),
            DiscoveryCandidate(
                place_id="restaurant-place",
                display_name="Fixture Restaurant",
                category="restaurant",
                business_status="OPERATIONAL",
                user_ratings_total=500,
                primary_type="restaurant",
            ),
        )

    async def aclose(self) -> None:
        return None


class FakeFreshnessProvider:
    provider_name = "places_api"

    def __init__(self) -> None:
        self.place_ids: list[str] = []

    async def fetch_review_freshness(self, place_id: str) -> ReviewFreshnessResult:
        self.place_ids.append(place_id)
        latest = datetime(2026, 7, 17, tzinfo=UTC)
        return ReviewFreshnessResult(
            latest_review_at=latest,
            payload=RawPlacePayload(
                request_variant="details_newest",
                review_sort="newest",
                fetched_at=latest,
                body={"status": "OK", "result": {"reviews": []}},
                payload_hash=f"hash-{place_id}",
            ),
        )

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_discovery_service_builds_catalog_and_report_from_fixtures() -> None:
    base_config = load_data_collection_config(Path("config/data_collection.yaml"))
    discovery = base_config.discovery.model_copy(update={"target_count": 2})
    config = base_config.model_copy(update={"discovery": discovery})
    existing = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(),
    )
    freshness = FakeFreshnessProvider()

    result = await DiscoveryService(FakeDiscoveryProvider(), freshness).run(
        config=config,
        existing_catalog=existing,
        target_count=2,
        as_of_date=date(2026, 7, 18),
    )

    assert len(result.catalog.venues) == 2
    assert {entry.category for entry in result.catalog.venues} == {
        "cafe",
        "restaurant",
    }
    assert sorted(freshness.place_ids) == ["cafe-place", "restaurant-place"]
    assert result.report["selected_new"] == 2
    assert result.report["catalog_categories"] == {"cafe": 1, "restaurant": 1}


@pytest.mark.asyncio
async def test_discovery_at_target_preserves_catalog_without_provider_calls() -> None:
    config = load_data_collection_config(Path("config/data_collection.yaml"))
    existing = VenueCatalog(
        region_slug="eryaman",
        region_name="Eryaman",
        venues=(
            VenueCatalogEntry(
                slug="existing-cafe",
                display_name="Existing Cafe",
                place_id="existing-place",
                category="cafe",
                brand_key="existing-cafe",
            ),
        ),
    )

    result = await DiscoveryService(
        FakeDiscoveryProvider(), FakeFreshnessProvider()
    ).run(
        config=config,
        existing_catalog=existing,
        target_count=1,
        as_of_date=date(2026, 7, 18),
    )

    assert result.catalog.venues == existing.venues
    assert result.report["candidate_count"] == 0
    assert result.report["existing_preserved"] == 1
