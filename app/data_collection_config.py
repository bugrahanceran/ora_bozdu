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


class DiscoveryQueryConfig(BaseModel):
    category: str
    text_query: str
    included_type: str


class DiscoveryConfig(BaseModel):
    target_count: int = Field(gt=0)
    minimum_candidate_pool: int = Field(gt=0)
    radius_meters: float = Field(gt=0, le=50000)
    page_size: int = Field(gt=0, le=20)
    min_user_ratings_total: int = Field(ge=0)
    max_branches_per_brand: int = Field(gt=0)
    queries: tuple[DiscoveryQueryConfig, ...]
    category_minimums: dict[str, int]
    brand_stopwords: tuple[str, ...] = ()
    brand_aliases: dict[str, str] = Field(default_factory=dict)
    stale_after_days: int = Field(gt=0)
    stale_penalty: float = Field(ge=0)
    review_count_log_weight: float = Field(gt=0)
    search_cache_path: Path
    report_path: Path

    @model_validator(mode="after")
    def validate_categories(self) -> "DiscoveryConfig":
        categories = [query.category for query in self.queries]
        if not categories or len(categories) != len(set(categories)):
            raise ValueError("discovery query categories must be non-empty and unique")
        unknown = set(self.category_minimums) - set(categories)
        if unknown:
            raise ValueError(f"category minimums have unknown categories: {unknown}")
        if any(minimum < 0 for minimum in self.category_minimums.values()):
            raise ValueError("category minimums cannot be negative")
        if sum(self.category_minimums.values()) > self.target_count:
            raise ValueError("category minimums exceed target_count")
        return self


class FetchConfig(BaseModel):
    cadence: Literal["daily", "weekly"]
    week_start: Literal[
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    ] = "monday"
    review_sorts: tuple[Literal["newest", "most_relevant"], ...]
    reviews_no_translations: bool
    fields: tuple[str, ...]

    @model_validator(mode="after")
    def validate_legacy_request(self) -> "FetchConfig":
        required_sorts = {"newest", "most_relevant"}
        if set(self.review_sorts) != required_sorts or len(self.review_sorts) != 2:
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
