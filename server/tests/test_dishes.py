from tests.helpers import plan_params


async def test_create_dishes_and_reject_duplicates(clients):
    payload = {"items": [{"dish_name": " Борщ ", "category": "Первое", "fixed_price": 100}]}
    r = await clients.admin.post("/dishes/dish", json=payload)
    assert r.status_code == 200 and r.json()["Result"]["created_count"] == 1

    r = await clients.admin.post("/dishes/dish", json=payload)
    assert r.status_code == 400  # такое блюдо уже есть

    r = await clients.admin.get("/dishes/dish", params={"name": "Борщ"})
    assert r.status_code == 200 and r.json()["dish"]["dish_name"] == "Борщ"


async def test_nutrition_round_trips_in_catalog_and_menu(clients):
    nutrition = {"serving_weight_g": 250.5, "energy_kcal": 180, "protein_g": 8.5, "fat_g": 4, "carbohydrates_g": 26}
    response = await clients.admin.post("/dishes/dish", json={"items": [
        {"dish_name": "Nutrition soup", "category": "Первое", "fixed_price": 100, **nutrition}
    ]})
    assert response.status_code == 200, response.text
    dish_id = response.json()["Result"]["created_dish_ids"][0]
    catalog = (await clients.admin.get("/admin/dishes")).json()["dishes"]
    assert all(next(d for d in catalog if d["id"] == dish_id)[key] == value for key, value in nutrition.items())
    menu = (await clients.student.get("/dishes/dishes_tomorrow")).json()["dishes"]
    assert not any(d["dish_id"] == dish_id for d in menu)
    assert (await clients.admin.patch("/dishes/dish", params={"dish_id": dish_id}, json={"protein_g": 9.5})).status_code == 200
    dish = (await clients.admin.get("/dishes/dish", params={"name": "Nutrition soup"})).json()["dish"]
    assert dish["protein_g"] == 9.5


async def test_negative_nutrition_is_rejected(clients):
    for key in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g"):
        body = {"dish_name": "Negative", "category": "Первое", "fixed_price": 10, key: -1}
        assert (await clients.admin.post("/dishes/dish", json={"items": [body]})).status_code == 422


async def test_category_whitespace_is_trimmed_and_empty_is_rejected(clients):
    item = {"dish_name": "Trimmed", "category": "  Салаты  ", "fixed_price": 10}
    response = await clients.admin.post("/dishes/dish", json={"items": [item]})
    assert response.status_code == 200, response.text
    dish_id = response.json()["Result"]["created_dish_ids"][0]
    dish = (await clients.admin.get("/dishes/dish", params={"name": "Trimmed"})).json()["dish"]
    assert dish["category"] == "Салаты"
    assert (await clients.admin.post("/dishes/dish", json={"items": [{**item, "dish_name": "Blank", "category": "   "}]})).status_code == 422
    assert (await clients.admin.patch("/dishes/dish", params={"dish_id": dish_id}, json={"category": "   "})).status_code == 422
    assert (await clients.admin.patch("/dishes/dish", params={"dish_id": dish_id}, json={"category": "  Десерт  "})).status_code == 200
    dish = (await clients.admin.get("/dishes/dish", params={"name": "Trimmed"})).json()["dish"]
    assert dish["category"] == "Десерт"


async def test_dish_validation(clients):
    bad = [
        {"dish_name": "A", "category": "Первое", "fixed_price": 0},
        {"dish_name": "A", "category": "", "fixed_price": 10},
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


async def test_supplier_cannot_plan_daily_menu(clients, world, menu):
    items = {"items": [{"dish_id": menu["soup"], "cart_quantity": 1}]}
    for days in (0, 2, 7, 8):
        assert (await clients.provider.put("/dishes/dishes", params=plan_params(world, days), json=items)).status_code == 403


async def test_legacy_plans_are_not_exposed_as_buffet_offerings(clients, menu):
    r = await clients.student.get("/dishes/dishes_tomorrow")
    assert r.json()["dishes"] == []
