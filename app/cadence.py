from datetime import date, timedelta

WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _week_start(value: date, *, week_start: str) -> date:
    try:
        start_index = WEEKDAY_INDEX[week_start]
    except KeyError as exc:
        raise ValueError(f"Unsupported week_start: {week_start}") from exc
    days_since_start = (value.weekday() - start_index) % 7
    return value - timedelta(days=days_since_start)


def period_start_for(
    snapshot_date: date,
    *,
    cadence: str,
    week_start: str,
    anchor_date: date | None = None,
) -> date:
    if cadence == "daily":
        return snapshot_date
    if cadence == "weekly":
        return _week_start(snapshot_date, week_start=week_start)
    if cadence != "biweekly":
        raise ValueError(f"Unsupported cadence: {cadence}")
    if anchor_date is None:
        raise ValueError("biweekly cadence requires an anchor_date")
    week_start_date = _week_start(snapshot_date, week_start=week_start)
    anchor_week_start = _week_start(anchor_date, week_start=week_start)
    weeks_diff = (week_start_date - anchor_week_start).days // 7
    if weeks_diff % 2 != 0:
        return week_start_date - timedelta(days=7)
    return week_start_date
