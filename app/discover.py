import argparse
import asyncio
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.adapters.places_legacy import (
    LegacyPlacesUnavailableError,
    PlacesLegacyAdapter,
)
from app.adapters.places_new import PlacesNewAccessError, PlacesNewTextSearchAdapter
from app.catalog import VenueCatalog, load_catalog, write_catalog
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
from app.services.discovery_service import build_discovery_result
from app.services.discovery_stages import (
    DiscoveryFreshnessStage,
    DiscoverySearchStage,
    complete_search_if_pool_ready,
    freshness_shortlist,
    search_stage_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover and deterministically select catalog venues"
    )
    subparsers = parser.add_subparsers(dest="stage", required=True)

    search = subparsers.add_parser("search", help="Run bounded Text Search pages")
    search.add_argument("--max-requests", type=int, required=True)
    search.add_argument("--target-count", type=int)
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
    subparsers.choices["finalize"].add_argument("--report", type=Path)
    return parser


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_context(args: argparse.Namespace):
    settings = get_settings()
    config_path = settings.data_collection_config_path
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
    requests_this_run: int = 0,
) -> dict:
    summary = search_stage_summary(
        cache,
        config=config,
        catalog=catalog,
        requests_this_run=requests_this_run,
    )
    payload = asdict(summary)
    required = summary.freshness_required
    payload["freshness_completed"] = (
        sum(
            place_id in cache.freshness_results
            for place_id in {
                candidate.place_id
                for candidate in freshness_shortlist(
                    cache,
                    config=config,
                    catalog=catalog,
                )
            }
        )
        if required is not None
        else 0
    )
    payload["as_of_date"] = cache.as_of_date.isoformat()
    payload["target_count"] = cache.target_count
    if cache.pages:
        latest = cache.pages[-1]
        latest_candidates = [
            candidate for candidate in cache.candidates[-latest.candidate_count :]
        ]
        payload["latest_page"] = {
            "category": latest.category,
            "candidate_count": latest.candidate_count,
            "has_next_page": latest.next_page_token is not None,
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
        target_count = args.target_count or config.discovery.target_count
        cache = create_search_cache(
            config=config,
            catalog=catalog,
            collection_config_hash=config_hash,
            catalog_hash=catalog_hash,
            target_count=target_count,
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
        if args.target_count is not None and args.target_count != cache.target_count:
            raise SystemExit("target_count changed; restart search with --reset")
        if args.date is not None and args.date != cache.as_of_date:
            raise SystemExit("selection date changed; restart search with --reset")

    if complete_search_if_pool_ready(cache, config=config, catalog=catalog):
        write_search_cache(cache_path, cache)
    if cache.search_completed or args.max_requests == 0:
        print(
            json.dumps(
                _status_payload(cache, config=config, catalog=catalog),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    adapter = PlacesNewTextSearchAdapter(
        _require_key(settings),
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=0 if args.no_retries else settings.http_max_retries,
    )
    try:
        summary = await DiscoverySearchStage(adapter).run(
            cache=cache,
            config=config,
            catalog=catalog,
            max_requests=args.max_requests,
            checkpoint=lambda value: write_search_cache(cache_path, value),
        )
    except PlacesNewAccessError as exc:
        raise SystemExit(
            "Places API (New) Text Search erişimi reddedildi. Google Cloud API "
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
        _catalog_path,
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
        _catalog_path,
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
    print(
        json.dumps(
            _status_payload(cache, config=config, catalog=catalog),
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
    freshness = {
        place_id: datetime.fromisoformat(value) if value else None
        for place_id, value in cache.freshness_results.items()
    }
    shortlisted = freshness_shortlist(cache, config=config, catalog=catalog)
    result = build_discovery_result(
        config=config,
        existing_catalog=catalog,
        target_count=cache.target_count,
        as_of_date=cache.as_of_date,
        searched=shortlisted,
        query_counts=dict(
            sorted(Counter(item.category for item in shortlisted).items())
        ),
        freshness_by_place_id=freshness,
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
