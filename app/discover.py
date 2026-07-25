import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.places_legacy import (
    LegacyPlacesUnavailableError,
    PlacesLegacyAdapter,
)
from app.adapters.places_nearby import PlacesNearbySearchAdapter, PlacesNewAccessError
from app.catalog import (
    VenueCatalog,
    load_catalog,
    load_other_region_place_ids,
    write_catalog,
)
from app.config import get_settings
from app.data_collection_config import (
    DataCollectionConfig,
    load_data_collection_config,
)
from app.discovery.search_cache import (
    DiscoverySearchCache,
    create_search_cache,
    load_search_cache,
    write_search_cache,
)
from app.discovery.selector import deduplicate_candidates
from app.services.discovery_service import build_discovery_result
from app.services.discovery_stages import (
    DiscoveryFreshnessStage,
    DiscoveryGridSearchStage,
    freshness_shortlist,
    grid_search_stage_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover and deterministically select catalog venues"
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    search = subparsers.add_parser("search", help="Run bounded Nearby Search cells")
    search.add_argument("--max-requests", type=int, required=True)
    search.add_argument("--date", type=date.fromisoformat)
    search.add_argument("--reset", action="store_true")
    search.add_argument("--no-retries", action="store_true")

    freshness = subparsers.add_parser(
        "freshness", help="Run bounded Legacy newest-review checks"
    )
    freshness.add_argument("--max-requests", type=int, required=True)
    freshness.add_argument("--no-retries", action="store_true")

    subparsers.add_parser("status", help="Show cached discovery progress")
    subparsers.add_parser(
        "finalize", help="Build catalog locally after freshness is complete"
    )

    for subparser in (
        search,
        freshness,
        subparsers.choices["status"],
        subparsers.choices["finalize"],
    ):
        subparser.add_argument("--catalog", type=Path)
        subparser.add_argument("--cache", type=Path)
        subparser.add_argument("--data-collection-config", type=Path)
    subparsers.choices["finalize"].add_argument("--report", type=Path)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_context(args: argparse.Namespace):
    settings = get_settings()
    config_path = args.data_collection_config or settings.data_collection_config_path
    config = load_data_collection_config(config_path)
    catalog_path = args.catalog or settings.venue_catalog_path
    catalog = load_catalog(catalog_path)
    if catalog.region_slug != config.region.slug:
        raise SystemExit("Catalog and data-collection config regions do not match")
    cache_path = args.cache or config.discovery.search_cache_path
    return (
        settings,
        config,
        catalog_path,
        catalog,
        cache_path,
        _sha256(config_path),
        _sha256(catalog_path),
    )


def _validate_cache(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    config_hash: str,
    catalog_hash: str,
) -> None:
    if cache.region_slug != config.region.slug:
        raise SystemExit("Discovery cache region does not match config")
    if cache.collection_config_hash != config_hash:
        raise SystemExit("Discovery config changed; restart search with --reset")
    if cache.catalog_hash != catalog_hash:
        raise SystemExit("Catalog changed; restart search with --reset")


def _require_key(settings) -> str:
    if settings.google_maps_api_key is None:
        raise SystemExit("GOOGLE_MAPS_API_KEY is required")
    return settings.google_maps_api_key.get_secret_value()


def _status_payload(
    cache: DiscoverySearchCache,
    *,
    config: DataCollectionConfig,
    catalog: VenueCatalog,
    cross_region_place_ids: frozenset[str] = frozenset(),
    requests_this_run: int = 0,
) -> dict:
    summary = grid_search_stage_summary(cache, requests_this_run=requests_this_run)
    payload = asdict(summary)
    payload["as_of_date"] = cache.as_of_date.isoformat()
    if cache.search_completed:
        required = freshness_shortlist(
            cache,
            config=config,
            catalog=catalog,
            cross_region_place_ids=cross_region_place_ids,
        )
        payload["freshness_required"] = len(required)
        payload["freshness_completed"] = sum(
            candidate.place_id in cache.freshness_results for candidate in required
        )
    else:
        payload["freshness_required"] = None
        payload["freshness_completed"] = 0
    if cache.cell_search_records:
        latest = cache.cell_search_records[-1]
        latest_cell = next(
            cell for cell in cache.cells if cell.cell_id == latest.cell_id
        )
        latest_candidates = (
            cache.candidates[-latest.candidate_count :]
            if latest.candidate_count
            else []
        )
        payload["latest_cell"] = {
            "cell_id": latest.cell_id,
            "center_latitude": latest_cell.center_latitude,
            "center_longitude": latest_cell.center_longitude,
            "radius_meters": latest_cell.radius_meters,
            "candidate_count": latest.candidate_count,
            "hit_result_cap": latest.hit_result_cap,
            "sample": [
                {
                    "place_id": candidate.place_id,
                    "display_name": candidate.display_name,
                    "business_status": candidate.business_status,
                    "user_ratings_total": candidate.user_ratings_total,
                    "primary_type": candidate.primary_type,
                }
                for candidate in latest_candidates[:5]
            ],
        }
    return payload


async def _run_search(args: argparse.Namespace) -> int:
    (
        settings,
        config,
        _catalog_path,
        catalog,
        cache_path,
        config_hash,
        catalog_hash,
    ) = _load_context(args)
    if args.reset or not cache_path.exists():
        as_of_date = args.date or datetime.now(ZoneInfo(settings.app_timezone)).date()
        cache = create_search_cache(
            config=config,
            collection_config_hash=config_hash,
            catalog_hash=catalog_hash,
            as_of_date=as_of_date,
        )
        write_search_cache(cache_path, cache)
    else:
        cache = load_search_cache(cache_path)
        _validate_cache(
            cache,
            config=config,
            config_hash=config_hash,
            catalog_hash=catalog_hash,
        )
        if args.date is not None and args.date != cache.as_of_date:
            raise SystemExit("selection date changed; restart search with --reset")

    if cache.search_completed or args.max_requests == 0:
        print(
            json.dumps(
                _status_payload(cache, config=config, catalog=catalog),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    adapter = PlacesNearbySearchAdapter(
        _require_key(settings),
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=0 if args.no_retries else settings.http_max_retries,
    )
    try:
        summary = await DiscoveryGridSearchStage(adapter).run(
            cache=cache,
            config=config,
            max_requests=args.max_requests,
            checkpoint=lambda value: write_search_cache(cache_path, value),
        )
    except PlacesNewAccessError as exc:
        raise SystemExit(
            "Places API (New) Nearby Search erişimi reddedildi. Google Cloud API "
            f"enablement, billing ve API-key restrictions kontrol edilmeli: {exc}"
        ) from exc
    finally:
        await adapter.aclose()
    print(
        json.dumps(
            _status_payload(
                cache,
                config=config,
                catalog=catalog,
                requests_this_run=summary.requests_this_run,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


async def _run_freshness(args: argparse.Namespace) -> int:
    (
        settings,
        config,
        catalog_path,
        catalog,
        cache_path,
        config_hash,
        catalog_hash,
    ) = _load_context(args)
    if not cache_path.exists():
        raise SystemExit("Discovery cache does not exist; run search first")
    cache = load_search_cache(cache_path)
    _validate_cache(
        cache,
        config=config,
        config_hash=config_hash,
        catalog_hash=catalog_hash,
    )
    cross_region_place_ids = load_other_region_place_ids(
        catalog_path, current_region_slug=config.region.slug
    )
    adapter = PlacesLegacyAdapter(
        _require_key(settings),
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=0 if args.no_retries else settings.http_max_retries,
        review_sorts=config.fetch.review_sorts,
        fields=config.fetch.fields,
        reviews_no_translations=config.fetch.reviews_no_translations,
    )
    try:
        summary = await DiscoveryFreshnessStage(adapter).run(
            cache=cache,
            config=config,
            catalog=catalog,
            max_requests=args.max_requests,
            checkpoint=lambda value: write_search_cache(cache_path, value),
            cross_region_place_ids=cross_region_place_ids,
        )
    except LegacyPlacesUnavailableError as exc:
        raise SystemExit(
            "Places API Legacy erişilemez; otomatik fallback yapılmadı. "
            f"Proje sahibiyle alternatif kararlaştırılmalı: {exc}"
        ) from exc
    finally:
        await adapter.aclose()
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


def _run_status(args: argparse.Namespace) -> int:
    (
        _settings,
        config,
        catalog_path,
        catalog,
        cache_path,
        config_hash,
        catalog_hash,
    ) = _load_context(args)
    if not cache_path.exists():
        raise SystemExit("Discovery cache does not exist")
    cache = load_search_cache(cache_path)
    _validate_cache(
        cache,
        config=config,
        config_hash=config_hash,
        catalog_hash=catalog_hash,
    )
    cross_region_place_ids = load_other_region_place_ids(
        catalog_path, current_region_slug=config.region.slug
    )
    print(
        json.dumps(
            _status_payload(
                cache,
                config=config,
                catalog=catalog,
                cross_region_place_ids=cross_region_place_ids,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_finalize(args: argparse.Namespace) -> int:
    (
        _settings,
        config,
        catalog_path,
        catalog,
        cache_path,
        config_hash,
        catalog_hash,
    ) = _load_context(args)
    if not cache_path.exists():
        raise SystemExit("Discovery cache does not exist")
    cache = load_search_cache(cache_path)
    _validate_cache(
        cache,
        config=config,
        config_hash=config_hash,
        catalog_hash=catalog_hash,
    )
    if not cache.search_completed:
        raise SystemExit("Search stage is not complete")
    cross_region_place_ids = load_other_region_place_ids(
        catalog_path, current_region_slug=config.region.slug
    )
    freshness = {
        place_id: datetime.fromisoformat(value) if value else None
        for place_id, value in cache.freshness_results.items()
    }
    shortlisted = freshness_shortlist(
        cache,
        config=config,
        catalog=catalog,
        cross_region_place_ids=cross_region_place_ids,
    )
    grid_summary = {
        "total_cells": len(cache.cells),
        "cells_searched": sum(1 for cell in cache.cells if cell.status == "searched"),
        "cells_split": sum(1 for cell in cache.cells if cell.status == "split"),
        "cells_flagged_for_review": len(cache.cells_flagged_for_review),
    }
    all_scanned_candidates = deduplicate_candidates(cache.domain_candidates())
    result = build_discovery_result(
        config=config,
        existing_catalog=catalog,
        as_of_date=cache.as_of_date,
        searched=shortlisted,
        grid_summary=grid_summary,
        freshness_by_place_id=freshness,
        all_scanned_candidates=all_scanned_candidates,
    )
    result.report["cross_region_duplicate_count"] = len(
        {candidate.place_id for candidate in cache.domain_candidates()}
        & cross_region_place_ids
    )
    write_catalog(catalog_path, result.catalog)
    report_path = args.report or config.discovery.report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result.report, ensure_ascii=False, indent=2))
    return 0


async def run(args: argparse.Namespace) -> int:
    if args.stage == "search":
        return await _run_search(args)
    if args.stage == "freshness":
        return await _run_freshness(args)
    if args.stage == "status":
        return _run_status(args)
    if args.stage == "finalize":
        return _run_finalize(args)
    raise AssertionError(f"Unknown stage: {args.stage}")


def main() -> None:
    raise SystemExit(asyncio.run(run(build_parser().parse_args())))


if __name__ == "__main__":
    main()
