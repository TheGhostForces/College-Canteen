from tests.helpers import plan_params


async def test_create_dishes_and_reject_duplicates(clients):
    payload = {"items": [{"dish_name": " Борщ ", "category": "Первое", "fixed_price": 100}]}
    r = await clients.admin.post("/dishes/dish", json=payload)
    assert r.status_code == 200 and r.json()["Result"]["created_count"] == 1

    r = await clients.admin.post("/dishes/dish", json=payload)
    assert r.status_code == 400  # такое блюдо уже есть

    r = await clients.admin.get("/dishes/dish", params={"name": "Борщ"})
    assert r.status_code == 200 and r.json()["dish"]["dish_name"] == "Борщ"


async def test_dish_validation(clients):
    bad = [
        {"dish_name": "A", "category": "Первое", "fixed_price": 0},
        {"dish_name": "A", "category": "Неизвестная", "fixed_price": 10},
        {"dish_name": "A", "category": "Первое", "fixed_price": 10, "img_url": "../../etc/passwd"},
    ]
    for item in bad:
        assert (await clients.admin.post("/dishes/dish", json={"items": [item]})).status_code == 422


async def test_deleted_dish_can_be_created_again(clients, menu):
    r = await clients.admin.delete("/dishes/dish", params={"dish_names": "Чай"})
    assert r.status_code == 200 and r.json()["data"]["deleted_count"] == 1

    r = await clients.admin.post(
        "/dishes/dish", json={"items": [{"dish_name": "Чай", "category": "Напитки", "fixed_price": 25}]}
    )
    assert r.status_code == 200 and r.json()["Result"]["created_dish_ids"] == [menu["tea"]]


async def test_delete_unknown_dish_is_404(clients):
    assert (await clients.admin.delete("/dishes/dish", params={"dish_ids": 999})).status_code == 404


async def test_admin_cannot_touch_other_institution(clients, menu):
    # блюдо принадлежит заведению 1, админ заведения 2 его "не видит"
    r = await clients.admin2.patch("/dishes/dish", params={"dish_id": menu["soup"]}, json={"fixed_price": 1})
    assert r.status_code == 404
    r = await clients.admin2.delete("/dishes/dish", params={"dish_ids": menu["soup"]})
    assert r.status_code == 404
    r = await clients.admin.patch("/dishes/dish", params={"dish_id": menu["soup"]}, json={"fixed_price": 110})
    assert r.status_code == 200


async def test_update_to_existing_name_conflicts(clients, menu):
    r = await clients.admin.patch("/dishes/dish", params={"dish_id": menu["tea"]}, json={"dish_name": "Борщ"})
    assert r.status_code == 409


async def test_planning_rules(clients, world, menu):
    items = {"items": [{"dish_id": menu["soup"], "cart_quantity": 1}]}
    assert (await clients.provider.put("/dishes/dishes", params=plan_params(world, 0), json=items)).status_code == 400
    assert (await clients.provider.put("/dishes/dishes", params=plan_params(world, 8), json=items)).status_code == 400
    assert (await clients.provider.put("/dishes/dishes", params=plan_params(world, 7), json=items)).status_code == 200

    dup = {"items": [{"dish_id": menu["soup"], "cart_quantity": 1}] * 2}
    assert (await clients.provider.put("/dishes/dishes", params=plan_params(world, 2), json=dup)).status_code == 400


async def test_student_sees_menu_with_remaining_quantity(clients, menu):
    r = await clients.student.get("/dishes/dishes_tomorrow")
    by_name = {d["dish_name"]: d for d in r.json()["dishes"]}
    assert by_name["Борщ"]["quantity"] == 5 and by_name["Чай"]["quantity"] == 3
