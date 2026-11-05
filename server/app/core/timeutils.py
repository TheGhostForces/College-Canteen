"""Время по часовому поясу колледжа.

В БД хранится "наивное" локальное время (без tzinfo), поэтому везде используем эти функции,
а не datetime.now()/date.today(): часовой пояс контейнера (UTC) не совпадает с московским.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def as_local_aware(value: datetime, timezone: ZoneInfo) -> datetime:
    """Convert an aware instant to the requested college time zone."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("an aware datetime is required")
    return value.astimezone(timezone)


def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)


def today_local() -> date:
    return now_local().date()


def tomorrow_local() -> date:
    return today_local() + timedelta(days=1)


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min)
