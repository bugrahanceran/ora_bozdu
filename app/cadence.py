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


def period_start_for(
    snapshot_date: date,
    *,
    cadence: str,
    week_start: str,
) -> date:
    if cadence == "daily":
        return snapshot_date
    if cadence != "weekly":
        raise ValueError(f"Unsupported cadence: {cadence}")
    try:
        start_index = WEEKDAY_INDEX[week_start]
    except KeyError as exc:
        raise ValueError(f"Unsupported week_start: {week_start}") from exc
    days_since_start = (snapshot_date.weekday() - start_index) % 7
    return snapshot_date - timedelta(days=days_since_start)
