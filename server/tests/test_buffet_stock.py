"""Buffet inventory is persistent; typed checkout reserves it atomically."""

import asyncio
from datetime import UTC, datetime

import pytest

from app.db.session import SessionFactory
from tests.test_meal_sets import make_dish


@pytest.fixture
def order_clock(monkeypatch):
    def set_time(day=2, hour=10, minute=0):
        instant = datetime(2026, 11, day, hour, minute, tzinfo=UTC)
        monkeypatch.setattr("app.api.routers.dishes.menu_now", lambda: instant)
        monkeypatch.setattr("app.repositories.baskets.menu_now", lambda: instant, raising=False)
        monkeypatch.setattr("app.repositories.orders.menu_now", lambda: instant, raising=False)

    set_time()
    return set_time


async def offer(clients, quantity=5):
    dish = await make_dish(clients.admin, "Buffet tea", energy_kcal=30)
    response = await clients.operator.post("/dishes/buffet", json={"dish_id": dish, "quantity": quantity})
    assert response.status_code == 200, response.text
    return dish, response.json()["offering"]["id"]


async def add(client, offering, quantity=1):
    return await client.post(
        "/basket/dish",
        json={
            "item_type": "buffet",
            "buffet_offering_id": offering,
            "cart_quantity": quantity,
        },
    )


async def inventory(clients):
    response = await clients.operator.get("/dishes/buffet")
    assert response.status_code == 200, response.text
    return response.json()["offerings"]


async def test_buffet_permissions_stock_adjustments_and_visibility(clients, order_clock):
    dish = await make_dish(clients.admin, "Tea")
    body = {"dish_id": dish, "quantity": 3}
    for client in (clients.student, clients.provider, clients.admin):
        assert (await client.post("/dishes/buffet", json=body)).status_code == 403
    assert (await clients.operator2.post("/dishes/buffet", json=body)).status_code == 404
    assert (await clients.operator.post("/dishes/buffet", json={**body, "quantity": -1})).status_code == 422
    response = await clients.operator.post("/dishes/buffet", json=body)
    assert response.status_code == 200, response.text
    offering = response.json()["offering"]["id"]
    for client in (clients.student, clients.provider, clients.admin):
        assert (await client.patch(f"/dishes/buffet/{offering}", json={"delta": 1})).status_code == 403
    assert (await clients.operator2.patch(f"/dishes/buffet/{offering}", json={"delta": 1})).status_code == 404
    assert (await clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": -4})).status_code == 400
    assert (await clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": 2})).status_code == 200
    assert (await clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": -1})).status_code == 200
    assert (await inventory(clients))[0]["quantity"] == 4
    assert len((await clients.student.get("/dishes/dishes_tomorrow")).json()["dishes"]) == 1
    await clients.operator.patch(f"/dishes/buffet/{offering}", json={"is_visible": False})
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["dishes"] == []
    assert (await add(clients.student, offering)).status_code == 404
    assert (await clients.operator2.get("/dishes/buffet")).json()["offerings"] == []


async def test_buffet_stock_carries_over_dates_and_scheduler(clients, order_clock):
    _, offering = await offer(clients)
    assert (await add(clients.student, offering, 2)).status_code == 200
    order_clock(day=4)
    from app.repositories.baskets import BasketRepository

    async with SessionFactory() as session:
        await BasketRepository(session).clear_stale_items()
    assert (await inventory(clients))[0]["quantity"] == 5
    response = await clients.student.post("/orders/order")
    assert response.status_code == 400 and "Cart updated" in response.text
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (await inventory(clients))[0]["quantity"] == 3
    data = (await clients.student.get("/orders/order")).json()
    [line] = next(iter(data["Orders"].values()))
    assert line["pickup_date"] == "2026-11-05"


async def test_cancel_hidden_offering_once_keeps_snapshots_and_visibility(clients, order_clock):
    dish, offering = await offer(clients, 3)
    assert (await add(clients.student, offering, 2)).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    await clients.operator.patch(f"/dishes/buffet/{offering}", json={"is_visible": False})
    await clients.admin.patch(
        "/dishes/dish", params={"dish_id": dish}, json={"dish_name": "Renamed", "fixed_price": 99, "energy_kcal": 99}
    )
    data = (await clients.student.get("/orders/order")).json()
    [line] = next(iter(data["Orders"].values()))
    assert (line["dish_name"], line["fixed_price"], line["energy_kcal"]) == ("Buffet tea", 20, 30)
    assert (await clients.student.delete("/orders/order")).status_code == 200
    assert (await clients.student.delete("/orders/order")).status_code == 404
    [stock] = await inventory(clients)
    assert stock["quantity"] == 3 and stock["is_visible"] is False
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["dishes"] == []


async def test_stale_stock_price_cart_requires_reconfirmation(clients, order_clock):
    dish, offering = await offer(clients, 4)
    assert (await add(clients.student, offering, 3)).status_code == 200
    await clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": -2})
    await clients.admin.patch("/dishes/dish", params={"dish_id": dish}, json={"fixed_price": 30})
    response = await clients.student.post("/orders/order")
    assert response.status_code == 400 and "Cart updated" in response.text
    assert (await inventory(clients))[0]["quantity"] == 2
    basket = (await clients.student.get("/basket/dish")).json()["dishes"]
    assert len(basket) == 1 and (basket[0]["quantity"], basket[0]["fixed_price"]) == (2, 30)
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (await inventory(clients))[0]["quantity"] == 0


async def test_two_concurrent_students_cannot_buy_last_buffet_unit(clients, order_clock):
    _, offering = await offer(clients, 1)
    assert (await add(clients.student, offering)).status_code == 200
    assert (await add(clients.student2, offering)).status_code == 200
    responses = await asyncio.gather(clients.student.post("/orders/order"), clients.student2.post("/orders/order"))
    assert sorted(r.status_code for r in responses) == [200, 400]
    assert (await inventory(clients))[0]["quantity"] == 0


async def test_concurrent_inventory_deltas_and_cancellation_are_not_lost(clients, order_clock):
    _, offering = await offer(clients, 2)
    assert (await add(clients.student, offering, 2)).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    responses = await asyncio.gather(
        clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": 1}),
        clients.operator.patch(f"/dishes/buffet/{offering}", json={"delta": 1}),
        clients.student.delete("/orders/order"),
        clients.student.delete("/orders/order"),
    )
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 404]
    assert (await inventory(clients))[0]["quantity"] == 4


async def test_concurrent_cancellations_restore_offerings_from_multiple_orders(clients, order_clock):
    _, first = await offer(clients, 2)
    dish = await make_dish(clients.admin, "Second offering")
    response = await clients.operator.post("/dishes/buffet", json={"dish_id": dish, "quantity": 2})
    second = response.json()["offering"]["id"]
    for client, sequence in ((clients.student, (first, second)), (clients.student2, (second, first))):
        for offering in sequence:
            assert (await add(client, offering)).status_code == 200
            assert (await client.post("/orders/order")).status_code == 200
    responses = await asyncio.wait_for(
        asyncio.gather(clients.student.delete("/orders/order"), clients.student2.delete("/orders/order")), timeout=5
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert [item["quantity"] for item in await inventory(clients)] == [2, 2]


async def test_opposite_set_insertion_orders_do_not_deadlock(clients, order_clock, monkeypatch):
    from app.repositories.baskets import BasketRepository

    dish = await make_dish(clients.admin, "Set component")
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    for kind in ("breakfast", "lunch"):
        response = await clients.admin.post(
            "/dishes/meal-sets",
            json={
                "cycle_week": 1,
                "weekday": 1,
                "meal_type": kind,
                "price": 50,
                "dish_ids": [dish],
            },
        )
        assert response.status_code == 200
    sets = (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"]
    ids = sorted(meal["id"] for meal in sets)
    for client, sequence in ((clients.student, ids), (clients.student2, list(reversed(ids)))):
        for meal_id in sequence:
            response = await client.post(
                "/basket/dish",
                json={
                    "item_type": "set",
                    "meal_set_id": meal_id,
                    "cart_quantity": 1,
                },
            )
            assert response.status_code == 200

    original = BasketRepository.typed_details
    first_locks = asyncio.Event()
    observed = {}

    async def synchronized_details(repo, item, lock=False):
        result = await original(repo, item, lock=lock)
        if lock and item.meal_set_id is not None:
            acquired = observed.setdefault(repo.session, [])
            acquired.append(item.meal_set_id)
            if len(acquired) == 1:
                if len(observed) == 2:
                    first_locks.set()
                try:
                    await asyncio.wait_for(first_locks.wait(), timeout=1.5)
                except TimeoutError:
                    pass  # With consistent ordering, the second checkout is blocked on this row.
        return result

    monkeypatch.setattr(BasketRepository, "typed_details", synchronized_details)
    responses = await asyncio.wait_for(
        asyncio.gather(clients.student.post("/orders/order"), clients.student2.post("/orders/order")), timeout=8
    )
    assert [response.status_code for response in responses] == [200, 200]
    assert len(observed) == 2
    assert all(sequence == ids for sequence in observed.values())


async def test_mixed_cart_locks_buffet_then_sets_by_id(clients, order_clock, monkeypatch):
    from app.repositories.baskets import BasketRepository

    _, first_offering = await offer(clients, 2)
    dish = await make_dish(clients.admin, "Mixed cart component")
    response = await clients.operator.post("/dishes/buffet", json={"dish_id": dish, "quantity": 2})
    assert response.status_code == 200
    second_offering = response.json()["offering"]["id"]
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    for kind in ("breakfast", "lunch"):
        assert (
            await clients.admin.post(
                "/dishes/meal-sets",
                json={
                    "cycle_week": 1,
                    "weekday": 1,
                    "meal_type": kind,
                    "price": 50,
                    "dish_ids": [dish],
                },
            )
        ).status_code == 200
    set_ids = sorted(meal["id"] for meal in (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"])
    for client in (clients.student, clients.student2):
        for meal_id in reversed(set_ids):
            assert (
                await client.post(
                    "/basket/dish",
                    json={
                        "item_type": "set",
                        "meal_set_id": meal_id,
                        "cart_quantity": 1,
                    },
                )
            ).status_code == 200
        for offering_id in (second_offering, first_offering):
            assert (await add(client, offering_id)).status_code == 200

    original = BasketRepository.typed_details
    observed = {}

    async def record_locks(repo, item, lock=False):
        result = await original(repo, item, lock=lock)
        if lock:
            key = (
                ("buffet", item.buffet_offering_id)
                if item.buffet_offering_id is not None
                else ("set", item.meal_set_id)
            )
            observed.setdefault(repo.session, []).append(key)
        return result

    monkeypatch.setattr(BasketRepository, "typed_details", record_locks)
    responses = await asyncio.wait_for(
        asyncio.gather(clients.student.post("/orders/order"), clients.student2.post("/orders/order")), timeout=8
    )
    assert [response.status_code for response in responses] == [200, 200]
    expected = [("buffet", first_offering), ("buffet", second_offering)] + [("set", value) for value in set_ids]
    assert len(observed) == 2 and all(sequence == expected for sequence in observed.values())
    assert [item["quantity"] for item in await inventory(clients)] == [0, 0]


async def test_changed_set_composition_requires_reconfirmation(clients, order_clock):
    first = await make_dish(clients.admin, "Original")
    second = await make_dish(clients.admin, "Replacement")
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    body = {"cycle_week": 1, "weekday": 1, "meal_type": "lunch", "price": 50, "dish_ids": [first]}
    assert (await clients.admin.post("/dishes/meal-sets", json=body)).status_code == 200
    [meal] = (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"]
    assert (
        await clients.student.post(
            "/basket/dish", json={"item_type": "set", "meal_set_id": meal["id"], "cart_quantity": 1}
        )
    ).status_code == 200
    assert (
        await clients.admin.put(f"/dishes/meal-sets/{meal['id']}", json={**body, "dish_ids": [second]})
    ).status_code == 200
    response = await clients.student.post("/orders/order")
    assert response.status_code == 400 and "Cart updated" in response.text
    [item] = (await clients.student.get("/basket/dish")).json()["dishes"]
    assert item["components"][0]["dish_name"] == "Replacement"
    assert (await clients.student.post("/orders/order")).status_code == 200


async def test_different_sets_allowed_duplicate_breakfast_rejected(clients, order_clock):
    dish = await make_dish(clients.admin, "Set component")
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    for kind in ("breakfast", "lunch"):
        response = await clients.admin.post(
            "/dishes/meal-sets",
            json={
                "cycle_week": 1,
                "weekday": 1,
                "meal_type": kind,
                "price": 50,
                "dish_ids": [dish],
            },
        )
        assert response.status_code == 200
    sets = (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"]
    for meal in sets:
        body = {"item_type": "set", "meal_set_id": meal["id"], "cart_quantity": 1}
        assert (await clients.student.post("/basket/dish", json=body)).status_code == 200
        assert (await clients.student.post("/basket/dish", json=body)).status_code == 400
    assert (await clients.student.post("/orders/order")).status_code == 200
    [lines] = (await clients.student.get("/orders/order")).json()["Orders"].values()
    assert {line["meal_type"] for line in lines} == {"breakfast", "lunch"}
    assert all(len(line["components"]) == 1 for line in lines)


@pytest.mark.parametrize(("hour", "minute", "expected"), [(12, 59, 200), (13, 0, 400)])
async def test_order_cutoff_at_1600_local(clients, order_clock, hour, minute, expected):
    _, offering = await offer(clients)
    assert (await add(clients.student, offering)).status_code == 200
    order_clock(hour=hour, minute=minute)  # Europe/Moscow = UTC + 3
    response = await clients.student.post("/orders/order")
    assert response.status_code == expected, response.text


async def test_hidden_cart_can_be_removed_and_cannot_be_checked_out(clients, order_clock):
    _, offering = await offer(clients)
    assert (await add(clients.student, offering)).status_code == 200
    await clients.operator.patch(f"/dishes/buffet/{offering}", json={"is_visible": False})
    response = await clients.student.post("/orders/order")
    assert response.status_code == 400
    assert (await clients.student.get("/basket/dish")).json()["dishes"] == []
    assert (await inventory(clients))[0]["quantity"] == 5


async def test_separate_orders_allow_different_set_types_but_reject_repeated_type(clients, order_clock):
    dish = await make_dish(clients.admin, "Set item")
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    for kind in ("breakfast", "lunch"):
        assert (
            await clients.admin.post(
                "/dishes/meal-sets",
                json={
                    "cycle_week": 1,
                    "weekday": 1,
                    "meal_type": kind,
                    "price": 50,
                    "dish_ids": [dish],
                },
            )
        ).status_code == 200
    sets = (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"]
    breakfast = next(x for x in sets if x["meal_type"] == "breakfast")
    lunch = next(x for x in sets if x["meal_type"] == "lunch")

    def body(meal):
        return {"item_type": "set", "meal_set_id": meal["id"], "cart_quantity": 1}

    assert (await clients.student.post("/basket/dish", json=body(breakfast))).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (await clients.student.post("/basket/dish", json=body(lunch))).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (await clients.student.post("/basket/dish", json=body(breakfast))).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 400


async def test_transferred_student_pickup_is_scoped_to_order_institution(clients, world, order_clock, monkeypatch):
    from datetime import date

    from sqlalchemy import update

    from app.db.models import UsersOrm

    _, old_offering = await offer(clients)
    assert (await add(clients.student, old_offering)).status_code == 200
    old_order = (await clients.student.post("/orders/order")).json()["Order"]["order_number"]
    async with SessionFactory() as session:
        await session.execute(update(UsersOrm).where(UsersOrm.email == "stud@x.ru").values(institution_id=world.inst2))
        await session.commit()
    dish = await make_dish(clients.admin2, "New college tea")
    response = await clients.operator2.post("/dishes/buffet", json={"dish_id": dish, "quantity": 2})
    new_offering = response.json()["offering"]["id"]
    assert (await add(clients.student, new_offering)).status_code == 200
    new_order = (await clients.student.post("/orders/order")).json()["Order"]["order_number"]
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    monkeypatch.setattr("app.api.routers.orders.today_local", lambda: date(2026, 11, 3))
    monkeypatch.setattr("app.repositories.orders.today_local", lambda: date(2026, 11, 3))
    response = await clients.operator2.post("/orders/student_order", json={"pickup_token": token})
    assert set(response.json()["Orders"]) == {new_order}
    assert (await clients.operator2.patch("/orders/order", json={"pickup_token": token})).status_code == 200
    assert set((await clients.student.get("/orders/order")).json()["Orders"]) == {old_order}


async def test_qr_fulfillment_and_history_retain_typed_snapshots(clients, order_clock, monkeypatch):
    from datetime import date

    dish, offering = await offer(clients)
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    assert (
        await clients.admin.post(
            "/dishes/meal-sets",
            json={
                "cycle_week": 1,
                "weekday": 1,
                "meal_type": "lunch",
                "price": 50,
                "dish_ids": [dish],
            },
        )
    ).status_code == 200
    [meal] = (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"]
    assert (await add(clients.student, offering)).status_code == 200
    assert (
        await clients.student.post(
            "/basket/dish", json={"item_type": "set", "meal_set_id": meal["id"], "cart_quantity": 1}
        )
    ).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (
        await clients.admin.patch("/dishes/dish", params={"dish_id": dish}, json={"dish_name": "New name"})
    ).status_code == 200
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    monkeypatch.setattr("app.api.routers.orders.today_local", lambda: date(2026, 11, 3))
    monkeypatch.setattr("app.repositories.orders.today_local", lambda: date(2026, 11, 3))
    response = await clients.operator.post("/orders/student_order", json={"pickup_token": token})
    assert response.status_code == 200
    [lines] = response.json()["Orders"].values()
    assert {line["item_type"] for line in lines} == {"buffet", "set"}
    assert next(line for line in lines if line["item_type"] == "set")["components"][0]["dish_name"] == "Buffet tea"
    assert next(line for line in lines if line["item_type"] == "set")["energy_kcal"] == 30
    assert (await clients.operator2.patch("/orders/order", json={"pickup_token": token})).status_code == 404
    assert (await clients.operator.patch("/orders/order", json={"pickup_token": token})).status_code == 200
    history = (await clients.student.get("/history/history")).json()["history"]
    assert len(history) == 1
    assert {line["item_type"] for line in history[0]["dishes"]} == {"buffet", "set"}
    assert next(line for line in history[0]["dishes"] if line["item_type"] == "buffet")["dish_name"] == "Buffet tea"
    assert next(line for line in history[0]["dishes"] if line["item_type"] == "buffet")["energy_kcal"] == 30


@pytest.mark.parametrize(("hour", "minute", "status", "remaining"), [(12, 59, 200, 2), (13, 0, 400, 1)])
async def test_cancellation_cutoff_uses_pickup_calendar(clients, order_clock, hour, minute, status, remaining):
    _, offering = await offer(clients, 2)
    assert (await add(clients.student, offering)).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    order_clock(hour=hour, minute=minute)
    assert (await clients.student.delete("/orders/order")).status_code == status
    assert (await inventory(clients))[0]["quantity"] == remaining


async def test_database_rejects_invalid_typed_cart_price(clients, order_clock):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    _, offering = await offer(clients, 2)
    assert (await add(clients.student, offering)).status_code == 200
    async with SessionFactory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(text('UPDATE "TypedCartItem" SET unit_price = 0'))
            await session.commit()
        await session.rollback()


async def test_legacy_scheduled_dish_cannot_be_added_to_student_cart(clients, menu, order_clock):
    response = await clients.student.post("/basket/dish", json={"dish_id": menu["soup"], "cart_quantity": 1})
    assert response.status_code == 422


async def test_downgrade_refuses_to_discard_typed_order_history(clients, order_clock):
    from alembic.config import Config
    from sqlalchemy import text

    from alembic import command

    _, offering = await offer(clients)
    assert (await add(clients.student, offering)).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    async with SessionFactory() as session:
        await session.execute(text("UPDATE \"Order\" SET order_status = 'COMPLETED'"))
        await session.commit()
    with pytest.raises(RuntimeError, match="downgrade"):
        await asyncio.to_thread(command.downgrade, Config("alembic.ini"), "0005")
    async with SessionFactory() as session:
        assert await session.scalar(text("SELECT version_num FROM alembic_version")) == "0006"
        assert await session.scalar(text('SELECT count(*) FROM "TypedOrderItem"')) == 1
        assert await session.scalar(text('SELECT count(*) FROM "BuffetOffering"')) == 1


async def test_sold_out_offerings_are_not_in_student_menu(clients, order_clock):
    _, offering = await offer(clients, 1)
    assert (await add(clients.student, offering)).status_code == 200
    cart = (await clients.student.get("/basket/dish")).json()["dishes"]
    assert cart[0]["energy_kcal"] == 30
    assert (await clients.student.post("/orders/order")).status_code == 200
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["dishes"] == []


async def test_expiration_keeps_typed_items_in_history(clients, order_clock, monkeypatch):
    from datetime import date

    from app.repositories.orders import OrdersRepository

    _, offering = await offer(clients, 2)
    assert (await add(clients.student, offering)).status_code == 200
    assert (await clients.student.post("/orders/order")).status_code == 200
    monkeypatch.setattr("app.repositories.orders.today_local", lambda: date(2026, 11, 4))
    async with SessionFactory() as session:
        assert await OrdersRepository(session).expire_overdue() == 1
    history = (await clients.student.get("/history/history")).json()["history"]
    assert history[0]["order_status"] == "expired"
    assert history[0]["dishes"][0]["item_type"] == "buffet"
    assert (await inventory(clients))[0]["quantity"] == 1
