import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.places_legacy import (
    LegacyPlacesUnavailableError,
    PlacesLegacyAdapter,
)
from app.catalog import load_catalog, sync_catalog
from app.config import get_settings
from app.data_collection_config import load_data_collection_config
from app.db import SessionLocal
from app.discovery.search_cache import load_search_cache
from app.scoring.config import load_scoring_config
from app.scoring.engine import ScoringEngine
from app.scoring.service import recompute_region
from app.services.fetch_service import FetchService


def configure_logging(log_level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx logs full request URLs, including the API key query parameter.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch periodic venue snapshots")
    parser.add_argument("--region", default="eryaman")
    parser.add_argument(
        "--venue",
        help="Fetch only the venue with this catalog slug",
    )
    parser.add_argument("--catalog", type=Path)
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Snapshot date in YYYY-MM-DD format; defaults to local today",
    )
    parser.add_argument(
        "--no-retries",
        action="store_true",
        help="Disable HTTP retries so the approved request ceiling is strict",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.google_maps_api_key is None:
        raise SystemExit("GOOGLE_MAPS_API_KEY is required")
    catalog_path = args.catalog or settings.venue_catalog_path
    catalog = load_catalog(catalog_path)
    collection_config = load_data_collection_config(
        settings.data_collection_config_path
    )
    if (
        catalog.region_slug != args.region
        or collection_config.region.slug != args.region
    ):
        raise SystemExit("Catalog, data-collection config and CLI regions must match")
    active_entries = tuple(entry for entry in catalog.venues if entry.active)
    if not active_entries:
        raise SystemExit("Catalog is empty; run app.discover first")
    if args.venue and args.venue not in {entry.slug for entry in active_entries}:
        raise SystemExit(f"Venue is not in the active catalog: {args.venue}")
    snapshot_date = args.date or datetime.now(ZoneInfo(settings.app_timezone)).date()
    adapter = PlacesLegacyAdapter(
        settings.google_maps_api_key.get_secret_value(),
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=0 if args.no_retries else settings.http_max_retries,
        review_sorts=collection_config.fetch.review_sorts,
        fields=collection_config.fetch.fields,
        reviews_no_translations=collection_config.fetch.reviews_no_translations,
    )
    seed_payloads_by_place_id = {}
    cache_path = collection_config.discovery.search_cache_path
    if cache_path.exists():
        discovery_cache = load_search_cache(cache_path)
        if discovery_cache.as_of_date == snapshot_date:
            seed_payloads_by_place_id = {
                place_id: (payload.to_domain(),)
                for place_id, payload in discovery_cache.freshness_payloads.items()
            }
    try:
        with SessionLocal() as session:
            sync_catalog(session, catalog)
            summary = await FetchService(adapter).run(
                session,
                region_slug=args.region,
                snapshot_date=snapshot_date,
                cadence=collection_config.fetch.cadence,
                week_start=collection_config.fetch.week_start,
                venue_slugs=tuple(entry.slug for entry in active_entries),
                venue_slug=args.venue,
                seed_payloads_by_place_id=seed_payloads_by_place_id,
            )
            recompute_region(
                session,
                region_slug=args.region,
                engine=ScoringEngine(load_scoring_config(settings.scoring_config_path)),
            )
    except LegacyPlacesUnavailableError as exc:
        raise SystemExit(
            "Places API Legacy erişilemez; otomatik fallback yapılmadı. "
            f"Proje sahibiyle alternatif kararlaştırılmalı: {exc}"
        ) from exc
    finally:
        await adapter.aclose()

    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 1 if summary.failed else 0


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
