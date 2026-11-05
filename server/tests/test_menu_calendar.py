from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionFactory
from app.services.menu_calendar import cycle_slot, next_pickup_day, ordering_open

MOSCOW = ZoneInfo("Europe/Moscow")


@pytest.mark.parametrize("day, expected", [
    (3, 6), (4, 6), (5, 6), (6, 7),
])
def test_next_pickup_skips_weekend_and_today(day, expected):
    assert next_pickup_day(datetime(2026, 7, day, 12, tzinfo=MOSCOW), MOSCOW) == date(2026, 7, expected)


def test_pickup_converts_to_local_date_first():
    assert next_pickup_day(datetime(2026, 7, 2, 22, tzinfo=timezone.utc), MOSCOW) == date(2026, 7, 6)


@pytest.mark.parametrize("second, expected", [(datetime(2026, 7, 5, 15, 59, 59, tzinfo=MOSCOW), True), (datetime(2026, 7, 5, 16, 0, tzinfo=MOSCOW), False)])
def test_monday_order_cutoff_is_sunday_at_four(second, expected):
    assert ordering_open(second, date(2026, 7, 6), MOSCOW) is expected


def test_cutoff_converts_timezone():
    assert not ordering_open(datetime(2026, 7, 5, 13, tzinfo=timezone.utc), date(2026, 7, 6), MOSCOW)


@pytest.mark.parametrize("day, expected", [(6, (1, 0)), (13, (2, 0)), (20, (1, 0)), (24, (1, 4))])
def test_cycle_slots_alternate(day, expected):
    assert cycle_slot(date(2026, 7, 6), date(2026, 7, day)) == expected


@pytest.mark.parametrize("anchor, pickup", [(date(2026, 7, 7), date(2026, 7, 7)), (date(2026, 7, 6), date(2026, 7, 11)), (date(2026, 7, 6), date(2026, 7, 3))])
def test_cycle_rejects_invalid_dates(anchor, pickup):
    with pytest.raises(ValueError):
        cycle_slot(anchor, pickup)


@pytest.mark.parametrize("function, args", [(next_pickup_day, (MOSCOW,)), (ordering_open, (date(2026, 7, 6), MOSCOW))])
def test_naive_datetimes_are_rejected(function, args):
    with pytest.raises(ValueError):
        function(datetime(2026, 7, 3, 12), *args)


async def test_institution_anchor_is_stored_and_must_be_monday():
    async with SessionFactory() as session:
        await session.execute(text('INSERT INTO "EducationInstitution" (name, cycle_start_monday) VALUES (:name, :anchor)'), {"name": "College", "anchor": date(2026, 7, 6)})
        assert await session.scalar(text('SELECT cycle_start_monday FROM "EducationInstitution" WHERE name = :name'), {"name": "College"}) == date(2026, 7, 6)
        with pytest.raises(IntegrityError):
            await session.execute(text('INSERT INTO "EducationInstitution" (name, cycle_start_monday) VALUES (:name, :anchor)'), {"name": "Invalid", "anchor": date(2026, 7, 7)})
        await session.rollback()


async def test_new_institution_has_no_anchor_until_configured():
    async with SessionFactory() as session:
        await session.execute(text('INSERT INTO "EducationInstitution" (name) VALUES (:name)'), {"name": "Unconfigured"})
        assert await session.scalar(text('SELECT cycle_start_monday FROM "EducationInstitution" WHERE name = :name'), {"name": "Unconfigured"}) is None
        await session.rollback()


def test_unconfigured_institution_cannot_produce_cycle_slot():
    with pytest.raises(ValueError):
        cycle_slot(None, date(2026, 7, 6))


def test_migration_leaves_existing_institutions_unconfigured():
    import asyncio

    import asyncpg
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    settings = get_settings()
    config = Config("alembic.ini")

    async def execute(sql):
        conn = await asyncpg.connect(
            user=settings.postgres_user,
            password=settings.postgres_password.get_secret_value() if settings.postgres_password is not None else None,
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_db,
        )
        try:
            return await conn.fetchval(sql)
        finally:
            await conn.close()

    command.downgrade(config, "0003")
    try:
        asyncio.run(execute('INSERT INTO "EducationInstitution" (name) VALUES (\'Existing\')'))
    finally:
        command.upgrade(config, "head")
    assert asyncio.run(execute('SELECT cycle_start_monday FROM "EducationInstitution" WHERE name = \'Existing\'')) is None
