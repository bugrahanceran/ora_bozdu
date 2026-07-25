from datetime import date

import pytest
from pydantic import ValidationError

from app.data_collection_config import FetchConfig

MINIMAL_FIELDS = (
    "name",
    "business_status",
    "rating",
    "user_ratings_total",
    "price_level",
    "reviews",
)


def make_fetch_config(**overrides: object) -> FetchConfig:
    defaults: dict[str, object] = {
        "cadence": "weekly",
        "review_sorts": ("newest",),
        "reviews_no_translations": True,
        "fields": MINIMAL_FIELDS,
    }
    defaults.update(overrides)
    return FetchConfig.model_validate(defaults)


def test_fetch_config_accepts_newest_only_review_sort() -> None:
    config = make_fetch_config()

    assert config.review_sorts == ("newest",)


def test_fetch_config_rejects_the_old_dual_sort_requirement() -> None:
    with pytest.raises(ValidationError, match="review_sorts"):
        make_fetch_config(review_sorts=("newest", "most_relevant"))


def test_fetch_config_rejects_most_relevant_only() -> None:
    with pytest.raises(ValidationError, match="review_sorts"):
        make_fetch_config(review_sorts=("most_relevant",))


def test_weekly_cadence_does_not_require_an_anchor_date() -> None:
    config = make_fetch_config(cadence="weekly")

    assert config.cadence_anchor_date is None


def test_biweekly_cadence_requires_an_anchor_date() -> None:
    with pytest.raises(ValidationError, match="anchor_date"):
        make_fetch_config(cadence="biweekly")


def test_biweekly_cadence_with_an_anchor_date_is_valid() -> None:
    config = make_fetch_config(
        cadence="biweekly", cadence_anchor_date=date(2026, 7, 13)
    )

    assert config.cadence == "biweekly"
    assert config.cadence_anchor_date == date(2026, 7, 13)
