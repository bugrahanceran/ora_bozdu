from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator


class CenterConfig(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RegionConfig(BaseModel):
    slug: str
    name: str
    center: CenterConfig


class DiscoveryConfig(BaseModel):
    radius_meters: float = Field(gt=0, le=50000)
    cell_radius_meters: float = Field(gt=0, le=50000)
    included_types: tuple[str, ...]
    excluded_types: tuple[str, ...] = ()
    excluded_primary_types: tuple[str, ...] = ()
    rank_preference: Literal["POPULARITY", "DISTANCE"] = "POPULARITY"
    max_result_count: int = Field(gt=0, le=20)
    min_user_ratings_total: int = Field(ge=0)
    tracked_venue_limit: int = Field(gt=0)
    brand_stopwords: tuple[str, ...] = ()
    brand_aliases: dict[str, str] = Field(default_factory=dict)
    stale_after_days: int = Field(gt=0)
    stale_penalty: float = Field(ge=0)
    review_count_log_weight: float = Field(gt=0)
    search_cache_path: Path
    report_path: Path

    @model_validator(mode="after")
    def validate_types(self) -> "DiscoveryConfig":
        if not self.included_types or len(self.included_types) != len(
            set(self.included_types)
        ):
            raise ValueError("included_types must be non-empty and unique")
        return self

    @model_validator(mode="after")
    def validate_cell_radius(self) -> "DiscoveryConfig":
        if self.cell_radius_meters > self.radius_meters:
            raise ValueError("cell_radius_meters must not exceed radius_meters")
        return self


class FetchConfig(BaseModel):
    cadence: Literal["daily", "weekly", "biweekly"]
    week_start: Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ] = "monday"
    cadence_anchor_date: date | None = None
    review_sorts: tuple[Literal["newest", "most_relevant"], ...]
    reviews_no_translations: bool
    fields: tuple[str, ...]

    @model_validator(mode="after")
    def validate_legacy_request(self) -> "FetchConfig":
        required_sorts = {"newest"}
        if set(self.review_sorts) != required_sorts or len(self.review_sorts) != len(
            required_sorts
        ):
            raise ValueError("fetch review_sorts must contain each required sort once")
        required_fields = {
            "name",
            "business_status",
            "rating",
            "user_ratings_total",
            "price_level",
            "reviews",
        }
        if set(self.fields) != required_fields or len(self.fields) != len(
            required_fields
        ):
            raise ValueError("fetch fields must match the approved minimal field set")
        return self

    @model_validator(mode="after")
    def validate_biweekly_anchor(self) -> "FetchConfig":
        if self.cadence == "biweekly" and self.cadence_anchor_date is None:
            raise ValueError("biweekly cadence requires a cadence_anchor_date")
        return self


class DataCollectionConfig(BaseModel):
    version: str
    region: RegionConfig
    discovery: DiscoveryConfig
    fetch: FetchConfig


def load_data_collection_config(path: Path) -> DataCollectionConfig:
    with path.open(encoding="utf-8") as config_file:
        return DataCollectionConfig.model_validate(yaml.safe_load(config_file))


@lru_cache
def get_data_collection_config(path: Path) -> DataCollectionConfig:
    return load_data_collection_config(path)
