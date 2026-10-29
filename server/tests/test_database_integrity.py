"""Database/repository regressions independent of authentication and HTTP fixtures."""

import asyncio
from datetime import timedelta

import pytest
from alembic.config import Config
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, tomorrow_local
from app.db.models import (
    DishesOrm,
    OrderDishOrm,
    ScheduleDishesOrm,
    ShoppingCartDishesOrm,
    ShoppingCartOrm,
    StudentsOrm,
    TemporaryCodeOrm,
    UsersOrm,
)
from app.db.session import SessionFactory
from app.repositories.baskets import BasketRepository
from app.repositories.dishes import DishesRepository
from app.repositories.orders import OrdersRepository
from app.schemas.dishes import DishPlan


@pytest.fixture
async def db_menu(world):
    async with SessionFactory() as session:
        students = list((await session.scalars(select(StudentsOrm.id).order_by(StudentsOrm.id))).all())
        dishes = [
            DishesOrm(dish_name="Soup", category="Первое", fixed_price=100, institution_id=world.inst1),
            DishesOrm(dish_name="Tea", category="Напитки", fixed_price=20, institution_id=world.inst1),
            DishesOrm(dish_name="Foreign", category="Второе", fixed_price=50, institution_id=world.inst2),
        ]
        session.add_all(dishes)
        await session.flush()
        schedules = [
            ScheduleDishesOrm(dish_id=dish.id, date=tomorrow_local(), quantity=20, total_quantity=20) for dish in dishes
        ]
        session.add_all(schedules)
        await session.commit()
        return {
            "students": students,
            "dishes": [dish.id for dish in dishes],
            "schedules": [schedule.id for schedule in schedules],
        }


async def _basket(method, *args):
    async with SessionFactory() as session:
        return await getattr(BasketRepository(session), method)(*args)


async def _orders(method, *args):
    async with SessionFactory() as session:
        return await getattr(OrdersRepository(session), method)(*args)


async def _stock(schedule_id):
    async with SessionFactory() as session:
        return await session.scalar(select(ScheduleDishesOrm.quantity).where(ScheduleDishesOrm.id == schedule_id))


async def _cart_quantity(student_id):
    async with SessionFactory() as session:
        return await session.scalar(
            select(func.coalesce(func.sum(ShoppingCartDishesOrm.cart_quantity), 0))
            .join(ShoppingCartOrm)
            .where(ShoppingCartOrm.student_id == student_id)
        )


@pytest.mark.parametrize(
    ("table", "assignment"),
    [
        ("Users", "role = 'superuser'"),
        ("Students", "date_end = date_start - 1"),
        ("TemporaryCode", "attempts = -1"),
        ("TemporaryCode", "expires_at = created_at"),
        ("Dishes", "fixed_price = 0"),
        ("Dishes", "category = 'unknown'"),
        ("ScheduleDishes", "quantity = -1"),
        ("ScheduleDishes", "quantity = total_quantity + 1"),
        ("ShoppingCartDishes", "cart_quantity = 0"),
        ("OrderDish", "cart_quantity = -1"),
        ("OrderDish", "unit_price = 0"),
        ("OrderDish", "unit_price = NULL"),
    ],
)
async def test_database_rejects_invalid_values(db_menu, table, assignment):
    student = db_menu["students"][0]
    dish = db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 1)
    await _orders("create_from_basket", student)
    await _basket("add_dish", student, dish, 1)
    async with SessionFactory() as session:
        now = now_local()
        session.add(
            TemporaryCodeOrm(
                code_hash="test-hash",
                attempts=0,
                created_at=now,
                expires_at=now + timedelta(minutes=10),
                user_id=await session.scalar(select(StudentsOrm.user_id).where(StudentsOrm.id == student)),
            )
        )
        await session.commit()
        with pytest.raises(IntegrityError):
            await session.execute(text(f'UPDATE "{table}" SET {assignment}'))
            await session.commit()
        await session.rollback()


async def test_planning_refreshes_stock_already_loaded_in_session(db_menu, world):
    student, dish, schedule_id = db_menu["students"][0], db_menu["dishes"][0], db_menu["schedules"][0]
    await _basket("add_dish", student, dish, 1)
    async with SessionFactory() as session:
        loaded = await session.get(ScheduleDishesOrm, schedule_id)
        assert loaded.quantity == 20
        await _orders("create_from_basket", student)
        plan = DishPlan(items=[{"dish_id": dish, "cart_quantity": 25}])
        await DishesRepository(session).set_plan_for_day(world.inst1, plan, tomorrow_local())
    assert await _stock(schedule_id) == 24


async def test_concurrent_initial_plans_are_serialized(db_menu, world):
    day = tomorrow_local() + timedelta(days=1)
    dish = db_menu["dishes"][0]

    async def plan(quantity):
        async with SessionFactory() as session:
            await DishesRepository(session).set_plan_for_day(
                world.inst1, DishPlan(items=[{"dish_id": dish, "cart_quantity": quantity}]), day
            )

    await asyncio.gather(plan(10), plan(15))
    async with SessionFactory() as session:
        rows = list(await session.scalars(select(ScheduleDishesOrm).where(ScheduleDishesOrm.date == day)))
        assert len(rows) == 1
        assert rows[0].quantity == rows[0].total_quantity
        assert rows[0].quantity in (10, 15)


@pytest.mark.parametrize("change", ["price", "quantity"])
async def test_checkout_rechecks_limits_after_cart_changes(db_menu, change):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 1)
    async with SessionFactory() as session:
        if change == "price":
            await session.execute(update(DishesOrm).where(DishesOrm.id == dish).values(fixed_price=1001))
        else:
            await session.execute(update(ShoppingCartDishesOrm).values(cart_quantity=6))
        await session.commit()
    with pytest.raises(BadRequestError):
        await _orders("create_from_basket", student)
    assert await _stock(db_menu["schedules"][0]) == 20
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(OrderDishOrm)) == 0


async def test_email_uniqueness_is_case_insensitive(world):
    async with SessionFactory() as session:
        session.add(UsersOrm(email="STUD@X.RU", role="student", institution_id=world.inst1))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_cart_student_is_unique_and_concurrent_creation_is_idempotent(db_menu):
    student = db_menu["students"][0]
    baskets = await asyncio.gather(*[_basket("create_for_student", student) for _ in range(3)])
    assert len({basket.id for basket in baskets}) == 1
    async with SessionFactory() as session:
        session.add(ShoppingCartOrm(student_id=student))
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


async def test_only_one_active_order_even_for_different_pickup_dates(db_menu):
    student = db_menu["students"][0]
    await _basket("add_dish", student, db_menu["dishes"][0], 1)
    await _orders("create_from_basket", student)
    async with SessionFactory() as session:
        # Same student on a different date is still a second active order.
        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    'INSERT INTO "Order" (order_number, order_status, created_at, pickup_date, student_id) '
                    "VALUES ('OTHER', 'IN_PROGRESS', now(), current_date + 2, :student)"
                ),
                {"student": student},
            )
            await session.commit()
        await session.rollback()
    await _orders("cancel_todays_order", student)
    await _basket("add_dish", student, db_menu["dishes"][0], 1)
    await _orders("create_from_basket", student)


async def test_repository_rejects_invalid_quantities(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    for quantity in (0, -1):
        with pytest.raises(BadRequestError):
            await _basket("add_dish", student, dish, quantity)
    await _basket("add_dish", student, dish, 1)
    with pytest.raises(BadRequestError):
        await _basket("set_quantity", student, dish, -1)
    assert await _cart_quantity(student) == 1


async def test_foreign_dishes_rejected_even_in_preexisting_cart(db_menu):
    student, foreign = db_menu["students"][0], db_menu["dishes"][2]
    with pytest.raises(NotFoundError):
        await _basket("add_dish", student, foreign, 1)
    basket = await _basket("create_for_student", student)
    async with SessionFactory() as session:
        session.add(
            ShoppingCartDishesOrm(shoppingcart_id=basket.id, schedule_dish_id=db_menu["schedules"][2], cart_quantity=1)
        )
        await session.commit()
    with pytest.raises(NotFoundError):
        await _basket("set_quantity", student, foreign, 2)
    with pytest.raises(BadRequestError, match="does not belong"):
        await _orders("create_from_basket", student)
    assert await _stock(db_menu["schedules"][2]) == 20
    assert await _cart_quantity(student) == 1


async def test_price_snapshot_is_used_by_all_order_outputs(db_menu, world):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 2)
    await _orders("create_from_basket", student)
    async with SessionFactory() as session:
        await session.execute(update(DishesOrm).where(DishesOrm.id == dish).values(fixed_price=999))
        await session.commit()
    student_orders = await _orders("get_student_orders", student)
    institution_orders = await _orders("get_institution_orders", world.inst1)
    for orders in (student_orders, institution_orders):
        [line] = next(iter(orders.values()))
        assert (line["fixed_price"], line["total_price"]) == (100, 200)
    await _orders("cancel_todays_order", student)
    now = now_local()
    [order] = await _orders("get_history", student, now.year, now.month)
    [line] = order["dishes"]
    assert (line["fixed_price"], line["total_price"]) == (100, 200)
    # A later order uses the new price, not the previous snapshot.
    async with SessionFactory() as session:
        await session.execute(update(DishesOrm).where(DishesOrm.id == dish).values(fixed_price=110))
        await session.commit()
    await _basket("add_dish", student, dish, 1)
    await _orders("create_from_basket", student)
    [line] = next(iter((await _orders("get_student_orders", student)).values()))
    assert line["fixed_price"] == 110


async def test_concurrent_cart_additions_do_not_lose_updates(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await asyncio.gather(*[_basket("add_dish", student, dish, 1) for _ in range(3)])
    assert await _cart_quantity(student) == 3


async def test_concurrent_cart_additions_cannot_bypass_total_limit(db_menu):
    student = db_menu["students"][0]
    results = await asyncio.gather(
        *[_basket("add_dish", student, dish, 3) for dish in db_menu["dishes"][:2]], return_exceptions=True
    )
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, BadRequestError) for result in results) == 1
    assert await _cart_quantity(student) == 3


async def test_concurrent_checkout_reserves_stock_once(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 2)
    results = await asyncio.gather(*[_orders("create_from_basket", student) for _ in range(2)], return_exceptions=True)
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, BadRequestError) for result in results) == 1
    assert await _stock(db_menu["schedules"][0]) == 18
    assert await _cart_quantity(student) == 0


async def test_concurrent_cancel_restores_stock_once(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 2)
    await _orders("create_from_basket", student)
    results = await asyncio.gather(*[_orders("cancel_todays_order", student) for _ in range(2)], return_exceptions=True)
    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, NotFoundError) for result in results) == 1
    assert await _stock(db_menu["schedules"][0]) == 20


async def test_cart_write_racing_checkout_is_not_silently_deleted(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 1)
    await asyncio.gather(_orders("create_from_basket", student), _basket("add_dish", student, dish, 1))
    async with SessionFactory() as session:
        ordered = await session.scalar(select(func.sum(OrderDishOrm.cart_quantity)))
    assert ordered + await _cart_quantity(student) == 2
    assert await _stock(db_menu["schedules"][0]) == 20 - ordered


async def test_two_students_cannot_oversell_stock(db_menu):
    dish, schedule = db_menu["dishes"][0], db_menu["schedules"][0]
    async with SessionFactory() as session:
        await session.execute(
            update(ScheduleDishesOrm).where(ScheduleDishesOrm.id == schedule).values(quantity=5, total_quantity=5)
        )
        await session.commit()
    for student in db_menu["students"]:
        await _basket("add_dish", student, dish, 3)
    results = await asyncio.gather(
        *[_orders("create_from_basket", student) for student in db_menu["students"]], return_exceptions=True
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    assert sum(isinstance(result, BadRequestError) for result in results) == 1
    assert await _stock(schedule) == 2


async def test_metadata_matches_migration_head():
    await asyncio.to_thread(command.check, Config("alembic.ini"))


async def _migrate(revision):
    await asyncio.to_thread(command.upgrade, Config("alembic.ini"), revision)


@pytest.mark.parametrize(
    ("invalid_sql", "repair_sql", "message"),
    [
        (
            "UPDATE \"Users\" SET email = 'STUD@X.RU' WHERE email = 'stud2@x.ru'",
            "UPDATE \"Users\" SET email = 'stud2@x.ru' WHERE email = 'STUD@X.RU'",
            "case-insensitive duplicate",
        ),
        (
            'UPDATE "Dishes" SET fixed_price = 0',
            'UPDATE "Dishes" SET fixed_price = 100',
            "ck_dishes_price",
        ),
        (
            "UPDATE \"Users\" SET role = 'unknown' WHERE email = 'stud@x.ru'",
            "UPDATE \"Users\" SET role = 'student' WHERE email = 'stud@x.ru'",
            "ck_users_role",
        ),
        (
            'UPDATE "Students" SET date_end = date_start - 1',
            "UPDATE \"Students\" SET date_end = '2030-01-01'",
            "ck_students_dates",
        ),
        (
            "UPDATE \"Dishes\" SET category = 'unknown'",
            "UPDATE \"Dishes\" SET category = 'Первое'",
            "ck_dishes_category",
        ),
        (
            'UPDATE "ScheduleDishes" SET quantity = -1',
            'UPDATE "ScheduleDishes" SET quantity = 20',
            "ck_schedule_quantities",
        ),
        (
            'INSERT INTO "Order" (student_id, order_number, order_status, created_at, pickup_date) '
            "SELECT id, 'LEGACY-1', 'IN_PROGRESS', now(), current_date + 1 FROM \"Students\" ORDER BY id LIMIT 1; "
            'INSERT INTO "Order" (student_id, order_number, order_status, created_at, pickup_date) '
            "SELECT id, 'LEGACY-2', 'IN_PROGRESS', now(), current_date + 2 FROM \"Students\" ORDER BY id LIMIT 1",
            'DELETE FROM "Order"',
            "multiple active orders",
        ),
        (
            'INSERT INTO "ShoppingCart" (student_id) SELECT id FROM "Students" ORDER BY id LIMIT 1; '
            'INSERT INTO "ShoppingCart" (student_id) SELECT id FROM "Students" ORDER BY id LIMIT 1',
            'DELETE FROM "ShoppingCart"',
            "multiple carts",
        ),
    ],
)
async def test_migration_refuses_legacy_data_without_silent_repairs(db_menu, invalid_sql, repair_sql, message):
    await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0002")
    try:
        async with SessionFactory() as session:
            for statement in invalid_sql.split("; "):
                await session.execute(text(statement))
            await session.commit()
        with pytest.raises(RuntimeError, match=message):
            await _migrate("head")
        async with SessionFactory() as session:
            assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0002"
            # The retry must still fail: the first attempt did not silently repair anything.
        with pytest.raises(RuntimeError, match=message):
            await _migrate("head")
    finally:
        async with SessionFactory() as session:
            await session.execute(text(repair_sql))
            await session.commit()
        await _migrate("head")


async def test_migration_backfills_legacy_order_prices(db_menu):
    student, dish = db_menu["students"][0], db_menu["dishes"][0]
    await _basket("add_dish", student, dish, 1)
    await _orders("create_from_basket", student)
    await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0002")
    try:
        await _migrate("head")
        async with SessionFactory() as session:
            [price] = list((await session.scalars(select(OrderDishOrm.unit_price))).all())
            assert price == 100
            await session.execute(update(DishesOrm).where(DishesOrm.id == dish).values(fixed_price=150))
            await session.commit()
            assert await session.scalar(select(OrderDishOrm.unit_price)) == 100
    finally:
        await _migrate("head")
