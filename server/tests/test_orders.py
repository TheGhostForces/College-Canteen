from sqlalchemy import select, update

from app.core.timeutils import today_local, tomorrow_local
from app.db.models import OrderOrm, ScheduleDishesOrm
from app.db.session import SessionFactory
from app.services.scheduler import nightly_cleanup
from tests.helpers import plan_params


async def _add(client, dish_id, quantity):
    return await client.post("/basket/dish", json={"dish_id": dish_id, "cart_quantity": quantity})


async def _remaining(dish_id):
    async with SessionFactory() as s:
        query = select(ScheduleDishesOrm.quantity).where(
            ScheduleDishesOrm.dish_id == dish_id, ScheduleDishesOrm.date == tomorrow_local()
        )
        return (await s.execute(query)).scalar_one()


async def _make_pickup_today():
    """Имитируем наступление дня выдачи: сдвигаем pickup_date всех заказов на сегодня."""
    async with SessionFactory() as s:
        await s.execute(update(OrderOrm).values(pickup_date=today_local()))
        await s.commit()


async def _student_id(client) -> int:
    return (await client.get("/orders/order")).json()["Student_ID"]


# ---------------- корзина ----------------
async def test_basket_rejects_invalid_quantities(clients, menu):
    s = clients.student
    assert (await _add(s, menu["soup"], 0)).status_code == 400
    assert (await s.post("/basket/dish", json={"dish_id": menu["soup"], "cart_quantity": -3})).status_code == 422
    assert (await _add(s, menu["soup"], 6)).status_code == 400


async def test_basket_accounts_for_items_already_in_cart(clients, menu):
    s = clients.student
    assert (await _add(s, menu["soup"], 3)).status_code == 200
    r = await _add(s, menu["soup"], 3)  # 3 + 3 > остатка 5
    assert r.status_code == 400 and "exceeds available" in r.json()["detail"]


async def test_basket_item_limit(clients, menu):
    s = clients.student
    assert (await _add(s, menu["soup"], 5)).status_code == 200
    r = await _add(s, menu["tea"], 1)
    assert r.status_code == 400 and r.json()["detail"] == "Too many dishes"


async def test_basket_amount_limit(clients, menu, world):
    r = await clients.admin.post(
        "/dishes/dish", json={"items": [{"dish_name": "Стейк", "category": "Второе", "fixed_price": 300}]}
    )
    steak = r.json()["Result"]["created_dish_ids"][0]
    await clients.provider.put(
        "/dishes/dishes", params=plan_params(world), json={"items": [{"dish_id": steak, "cart_quantity": 5}]}
    )
    r = await _add(clients.student, steak, 4)  # 4 * 300 = 1200 > 1000
    assert r.status_code == 400 and "exceeds" in r.json()["detail"]


async def test_change_quantity_checks_stock_and_zero_removes(clients, menu):
    s = clients.student
    await _add(s, menu["tea"], 1)
    assert (await s.post("/basket/quantity", json={"dish_id": menu["tea"], "cart_quantity": 4})).status_code == 400
    assert (await s.post("/basket/quantity", json={"dish_id": menu["tea"], "cart_quantity": 3})).status_code == 200
    assert (await s.post("/basket/quantity", json={"dish_id": menu["tea"], "cart_quantity": 0})).status_code == 200
    assert (await s.get("/basket/dish")).json()["dishes"] == []
    assert (await s.delete("/basket/dish", params={"dish_id": menu["tea"]})).status_code == 404


async def test_deleted_dish_cannot_be_ordered(clients, menu):
    await clients.admin.delete("/dishes/dish", params={"dish_ids": menu["tea"]})
    assert (await _add(clients.student, menu["tea"], 1)).status_code == 404


# ---------------- заказы ----------------
async def test_order_flow_reserves_and_cancel_restores_stock(clients, menu):
    s = clients.student
    await _add(s, menu["soup"], 2)
    r = await s.post("/orders/order")
    assert r.status_code == 200 and r.json()["Order"]["order_number"].startswith("ORD-")
    assert await _remaining(menu["soup"]) == 3
    assert (await s.get("/basket/dish")).json()["dishes"] == []

    assert (await s.post("/orders/order")).status_code == 400  # корзина пуста / заказ уже есть

    r = await s.get("/orders/order")
    assert len(r.json()["Orders"]) == 1

    assert (await s.delete("/orders/order")).status_code == 200
    assert await _remaining(menu["soup"]) == 5


async def test_cannot_have_two_active_orders(clients, menu):
    s = clients.student
    await _add(s, menu["soup"], 1)
    await s.post("/orders/order")
    await _add(s, menu["tea"], 1)
    r = await s.post("/orders/order")
    assert r.status_code == 400 and r.json()["detail"] == "Order already exists"


async def test_stock_is_not_oversold(clients, menu):
    await _add(clients.student, menu["tea"], 3)
    await _add(clients.student2, menu["tea"], 3)
    assert (await clients.student.post("/orders/order")).status_code == 200
    r = await clients.student2.post("/orders/order")
    assert r.status_code == 400 and "Cart updated" in r.json()["detail"]
    assert await _remaining(menu["tea"]) == 0


async def test_cancel_deadline(clients, menu, monkeypatch):
    from datetime import datetime

    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    monkeypatch.setattr("app.api.routers.orders.now_local", lambda: datetime(2026, 1, 1, 16, 0))
    r = await clients.student.delete("/orders/order")
    assert r.status_code == 400 and r.json()["detail"] == "Not enough time"


async def test_replanning_keeps_already_ordered_portions(clients, menu, world):
    await _add(clients.student, menu["soup"], 2)
    await clients.student.post("/orders/order")  # заказано 2 из 5

    put = lambda qty: clients.provider.put(  # noqa: E731
        "/dishes/dishes", params=plan_params(world), json={"items": [{"dish_id": menu["soup"], "cart_quantity": qty}]}
    )
    assert (await put(10)).status_code == 200
    assert await _remaining(menu["soup"]) == 8  # 10 - 2 заказанных, а не 10
    assert (await put(1)).status_code == 409  # меньше уже заказанного нельзя

    r = await clients.provider.get("/orders/total_quantity", params={"institution_id": world.inst1})
    soup = next(d for d in r.json()["dishes"] if d["dish_id"] == menu["soup"])
    assert (soup["total_quantity"], soup["ordered_quantity"], soup["remains_quantity"]) == (10, 2, 8)


# ---------------- оператор раздачи ----------------
async def test_operator_sees_only_orders_due_today(clients, menu):
    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]

    # заказ оформлен на завтра: сегодня оператору нечего выдавать
    r = await clients.operator.post("/orders/student_order", json={"pickup_token": token})
    assert r.status_code == 200 and r.json()["Orders"] == {}
    assert (await clients.operator.patch("/orders/order", json={"pickup_token": token})).status_code == 404

    await _make_pickup_today()
    r = await clients.operator.post("/orders/student_order", json={"pickup_token": token})
    assert len(r.json()["Orders"]) == 1
    assert (await clients.operator.patch("/orders/order", json={"pickup_token": token})).status_code == 200
    assert (await clients.operator.patch("/orders/order", json={"pickup_token": token})).status_code == 404  # уже выдан


async def test_operator_cannot_access_other_institution_students(clients, menu):
    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    await _make_pickup_today()

    assert (await clients.operator2.post("/orders/student_order", json={"pickup_token": token})).status_code == 404
    assert (await clients.operator2.patch("/orders/order", json={"pickup_token": token})).status_code == 404


async def test_history_and_expiration(clients, menu):
    s = clients.student
    await _add(s, menu["soup"], 1)
    await s.post("/orders/order")
    assert (await s.get("/history/history")).json()["history"] == []  # активные заказы в историю не попадают

    # день выдачи прошёл, заказ не забрали -> ночная задача помечает его просроченным
    await _expire_marker()
    await nightly_cleanup()
    history = (await s.get("/history/history")).json()["history"]
    assert [h["order_status"] for h in history] == ["expired"]
    assert (await s.get("/history/history", params={"month": 13})).status_code == 422


async def _expire_marker():
    from datetime import timedelta

    async with SessionFactory() as session:
        await session.execute(update(OrderOrm).values(pickup_date=today_local() - timedelta(days=1)))
        await session.commit()


async def test_order_created_just_after_midnight_is_not_expired_early(clients, menu):
    """Регрессия: заказ, оформленный в 00:30 (выдача сегодня), ночная задача раньше гасила."""
    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    await _make_pickup_today()
    await nightly_cleanup()
    assert len((await clients.student.get("/orders/order")).json()["Orders"]) == 1


async def test_pickup_token_is_short_lived_and_student_only(clients, anon, world):
    from datetime import UTC, datetime

    import jwt

    from app.core.config import get_settings

    r = await clients.student.post("/orders/pickup_token")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    data = r.json()
    claims = jwt.decode(data["pickup_token"], get_settings().secret_key.get_secret_value(), algorithms=["HS256"])
    assert claims["purpose"] == "pickup"
    assert claims["student_id"] == await _student_id(clients.student)
    assert claims["institution_id"] == world.inst1
    assert int(claims["sub"]) > 0
    assert 0 < claims["exp"] - datetime.now(UTC).timestamp() <= 300
    assert datetime.fromisoformat(data["expires_at"]).timestamp() == claims["exp"]
    assert (await anon.post("/orders/pickup_token")).status_code == 401
    for client in (clients.operator, clients.admin, clients.provider):
        assert (await client.post("/orders/pickup_token")).status_code == 403


async def test_numeric_pickup_bypass_is_rejected(clients, menu):
    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    await _make_pickup_today()
    sid = await _student_id(clients.student)
    assert (await clients.operator.get("/orders/student_order", params={"student_id": sid})).status_code == 405
    assert (await clients.operator.patch("/orders/order", params={"student_id": sid})).status_code == 422
    for method, path in (("post", "/orders/student_order"), ("patch", "/orders/order")):
        call = getattr(clients.operator, method)
        assert (await call(path, json={"student_id": sid})).status_code == 422
        assert (await call(path, json={"pickup_token": str(sid)})).status_code == 400
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    r = await clients.operator.post("/orders/student_order", json={"pickup_token": token})
    assert len(r.json()["Orders"]) == 1


async def test_invalid_pickup_tokens_rejected_at_search_and_completion(clients, menu, world):
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.core.config import get_settings

    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    await _make_pickup_today()
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    key = get_settings().secret_key.get_secret_value()
    claims = jwt.decode(token, key, algorithms=["HS256"])
    invalid = [
        jwt.encode({**claims, "exp": datetime.now(UTC) - timedelta(seconds=1)}, key, algorithm="HS256"),
        jwt.encode({**claims, "purpose": "access"}, key, algorithm="HS256"),
        jwt.encode(claims, "wrong-signing-key-that-is-at-least-32-bytes", algorithm="HS256"),
        clients.student.cookies.get("access_token").removeprefix("Bearer "),
        "not-a-jwt",
    ]
    for missing in ("exp", "purpose", "sub", "student_id", "institution_id"):
        invalid.append(jwt.encode({k: v for k, v in claims.items() if k != missing}, key, algorithm="HS256"))
    for token_value in invalid:
        for method, path in (("post", "/orders/student_order"), ("patch", "/orders/order")):
            r = await getattr(clients.operator, method)(path, json={"pickup_token": token_value})
            assert r.status_code == 400, r.text
    for changed in ({"sub": "99999"}, {"institution_id": world.inst2}, {"student_id": 99999}):
        forged = jwt.encode({**claims, **changed}, key, algorithm="HS256")
        for method, path in (("post", "/orders/student_order"), ("patch", "/orders/order")):
            r = await getattr(clients.operator, method)(path, json={"pickup_token": forged})
            assert r.status_code == 404, r.text
    assert (await clients.operator.patch("/orders/order", json={"pickup_token": token})).status_code == 200


async def test_pickup_rechecks_current_institution(clients, menu, world):
    from app.db.models import UsersOrm

    await _add(clients.student, menu["soup"], 1)
    await clients.student.post("/orders/order")
    await _make_pickup_today()
    token = (await clients.student.post("/orders/pickup_token")).json()["pickup_token"]
    async with SessionFactory() as session:
        await session.execute(update(UsersOrm).where(UsersOrm.email == "stud@x.ru").values(institution_id=world.inst2))
        await session.commit()
    for operator in (clients.operator, clients.operator2):
        r = await operator.post("/orders/student_order", json={"pickup_token": token})
        assert r.status_code == 404
        r = await operator.patch("/orders/order", json={"pickup_token": token})
        assert r.status_code == 404
