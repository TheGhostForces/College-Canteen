"""Weekday pickup dates and the institution's repeating two-week menu."""

from datetime import date, datetime, time, timedelta, timezone as utc_timezone
from zoneinfo import ZoneInfo

from app.core.timeutils import as_local_aware


def next_pickup_day(now: datetime, timezone: ZoneInfo) -> date:
    day = as_local_aware(now, timezone).date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def ordering_open(now: datetime, pickup_day: date, timezone: ZoneInfo) -> bool:
    local_now = as_local_aware(now, timezone)
    cutoff = datetime.combine(pickup_day - timedelta(days=1), time(16), tzinfo=timezone)
    return local_now.astimezone(utc_timezone.utc) < cutoff.astimezone(utc_timezone.utc)


def cycle_slot(start_monday: date | None, pickup_day: date) -> tuple[int, int]:
    if start_monday is None or start_monday.weekday() != 0 or pickup_day.weekday() >= 5 or pickup_day < start_monday:
        raise ValueError("cycle requires a Monday anchor and a weekday on or after it")
    return ((pickup_day - start_monday).days // 7 % 2 + 1, pickup_day.weekday())
