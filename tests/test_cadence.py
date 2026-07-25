from datetime import date

import pytest

from app.cadence import period_start_for

ANCHOR = date(2026, 7, 13)  # a Monday


def test_daily_returns_the_snapshot_date_unchanged() -> None:
    assert period_start_for(
        date(2026, 7, 22), cadence="daily", week_start="monday"
    ) == date(2026, 7, 22)


def test_weekly_returns_the_configured_weekday_start() -> None:
    assert period_start_for(
        date(2026, 7, 22), cadence="weekly", week_start="monday"
    ) == date(2026, 7, 20)


def test_biweekly_anchor_week_itself_returns_its_own_week_start() -> None:
    # 2026-07-15 falls in the anchor's own week (2026-07-13 .. 2026-07-19).
    assert period_start_for(
        date(2026, 7, 15), cadence="biweekly", week_start="monday", anchor_date=ANCHOR
    ) == date(2026, 7, 13)


def test_biweekly_one_week_after_anchor_rolls_back_to_the_anchor_period() -> None:
    # 2026-07-22 is in the week immediately after the anchor week -- an odd
    # number of weeks away, so it belongs to the *same* two-week period as
    # the anchor, not a new one.
    assert period_start_for(
        date(2026, 7, 22), cadence="biweekly", week_start="monday", anchor_date=ANCHOR
    ) == date(2026, 7, 13)


def test_biweekly_two_weeks_after_anchor_starts_the_next_period() -> None:
    # 2026-07-29 is two weeks after the anchor week -- an even offset, so it
    # starts a new biweekly period at 2026-07-27.
    assert period_start_for(
        date(2026, 7, 29), cadence="biweekly", week_start="monday", anchor_date=ANCHOR
    ) == date(2026, 7, 27)


def test_biweekly_before_the_anchor_date_still_aligns_to_a_period() -> None:
    # 2026-07-08 is one week before the anchor week -- an odd (negative)
    # offset, so it rolls back to the period starting 2026-06-29, not
    # 2026-07-06.
    assert period_start_for(
        date(2026, 7, 8), cadence="biweekly", week_start="monday", anchor_date=ANCHOR
    ) == date(2026, 6, 29)


def test_biweekly_honors_a_non_monday_week_start() -> None:
    thursday_anchor = date(2026, 7, 16)  # a Thursday
    assert period_start_for(
        date(2026, 7, 23),
        cadence="biweekly",
        week_start="thursday",
        anchor_date=thursday_anchor,
    ) == date(2026, 7, 16)


def test_biweekly_without_anchor_date_raises() -> None:
    with pytest.raises(ValueError, match="anchor_date"):
        period_start_for(date(2026, 7, 22), cadence="biweekly", week_start="monday")


def test_unsupported_cadence_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported cadence"):
        period_start_for(date(2026, 7, 22), cadence="monthly", week_start="monday")


def test_unsupported_week_start_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported week_start"):
        period_start_for(date(2026, 7, 22), cadence="weekly", week_start="someday")
