import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Region, Venue


@dataclass(frozen=True, slots=True)
class VenueCatalogEntry:
    slug: str
    display_name: str
    place_id: str
    category: str
    brand_key: str
    active: bool = True


@dataclass(frozen=True, slots=True)
class VenueCatalog:
    region_slug: str
    region_name: str
    venues: tuple[VenueCatalogEntry, ...]
    version: str = "catalog.v1"


def load_catalog(path: Path) -> VenueCatalog:
    with path.open(encoding="utf-8") as catalog_file:
        data = yaml.safe_load(catalog_file) or {}
    region = data["region"]
    venues = tuple(
        VenueCatalogEntry(
            slug=item["slug"],
            display_name=item["display_name"],
            place_id=item["place_id"],
            category=item["category"],
            brand_key=item["brand_key"],
            active=item.get("active", True),
        )
        for item in data.get("venues", [])
    )
    slugs = [venue.slug for venue in venues]
    place_ids = [venue.place_id for venue in venues]
    if len(slugs) != len(set(slugs)):
        raise ValueError(f"Venue catalog contains duplicate slugs: {path}")
    if len(place_ids) != len(set(place_ids)):
        raise ValueError(f"Venue catalog contains duplicate place IDs: {path}")
    if any(not place_id for place_id in place_ids):
        raise ValueError(f"Every catalog venue must have a place_id: {path}")
    return VenueCatalog(
        version=data.get("version", "catalog.v1"),
        region_slug=region["slug"],
        region_name=region["name"],
        venues=venues,
    )


def write_catalog(path: Path, catalog: VenueCatalog) -> None:
    payload = {
        "version": catalog.version,
        "region": {"slug": catalog.region_slug, "name": catalog.region_name},
        "venues": [asdict(venue) for venue in catalog.venues],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def sync_catalog(session: Session, catalog: VenueCatalog) -> Region:
    region = session.scalar(select(Region).where(Region.slug == catalog.region_slug))
    if region is None:
        region = Region(slug=catalog.region_slug, name=catalog.region_name)
        session.add(region)
        session.flush()
    else:
        region.name = catalog.region_name

    existing_venues = list(
        session.scalars(select(Venue).where(Venue.region_id == region.id)).all()
    )
    by_slug = {venue.slug: venue for venue in existing_venues}
    by_place_id = {
        venue.provider_place_id: venue
        for venue in existing_venues
        if venue.provider_place_id
    }
    catalog_slugs: set[str] = set()
    for entry in catalog.venues:
        venue = by_place_id.get(entry.place_id) or by_slug.get(entry.slug)
        if venue is None:
            venue = Venue(
                region_id=region.id,
                slug=entry.slug,
                display_name=entry.display_name,
                provider="places_api",
                provider_place_id=entry.place_id,
                is_active=entry.active,
            )
            session.add(venue)
        else:
            venue.slug = entry.slug
            venue.display_name = entry.display_name
            venue.provider = "places_api"
            venue.provider_place_id = entry.place_id
            venue.is_active = entry.active
        catalog_slugs.add(entry.slug)

    for venue in existing_venues:
        if venue.slug not in catalog_slugs:
            venue.is_active = False

    session.commit()
    return region


def main() -> None:
    from app.config import get_settings
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description="Sync the venue catalog to the DB")
    parser.add_argument("--catalog", type=Path)
    args = parser.parse_args()
    catalog = load_catalog(args.catalog or get_settings().venue_catalog_path)
    with SessionLocal() as session:
        sync_catalog(session, catalog)
    print(
        json.dumps(
            {
                "region": catalog.region_slug,
                "venues": len(catalog.venues),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
