"""Время по часовому поясу колледжа.

В БД хранится "наивное" локальное время (без tzinfo), поэтому везде используем эти функции,
а не datetime.now()/date.today(): часовой пояс контейнера (UTC) не совпадает с московским.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def now_local() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone)).replace(tzinfo=None)


def today_local() -> date:
    return now_local().date()


def tomorrow_local() -> date:
    return today_local() + timedelta(days=1)


def start_of_day(day: date) -> datetime:
    return datetime.combine(day, time.min)
