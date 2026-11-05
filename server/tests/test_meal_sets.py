from datetime import UTC, datetime

import pytest


async def make_dish(client, name, **nutrition):
    r = await client.post(
        "/dishes/dish", json={"items": [{"dish_name": name, "category": "Food", "fixed_price": 20, **nutrition}]}
    )
    assert r.status_code == 200, r.text
    return r.json()["Result"]["created_dish_ids"][0]


@pytest.mark.parametrize("week", [1, 2])
@pytest.mark.parametrize("meal_type", ["breakfast", "lunch", "afternoon_snack", "dinner"])
async def test_admin_saves_and_reads_all_slots(clients, week, meal_type):
    dish = await make_dish(clients.admin, "Soup")
    assert (
        await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    ).status_code == 200
    body = {"cycle_week": week, "weekday": 1, "meal_type": meal_type, "price": 55, "dish_ids": [dish]}
    r = await clients.admin.post("/dishes/meal-sets", json=body)
    assert r.status_code == 200, r.text
    data = (await clients.admin.get("/dishes/meal-sets")).json()
    assert data["cycle_start_monday"] == "2026-11-02"
    assert len(data["sets"]) == 1
    assert all(data["sets"][0][k] == v for k, v in body.items())
    assert (await clients.admin.post("/dishes/meal-sets", json=body)).status_code == 409
    assert (await clients.admin2.get("/dishes/meal-sets")).json()["sets"] == []


async def test_permissions_and_validation(clients):
    foreign = await make_dish(clients.admin2, "Other")
    own = await make_dish(clients.admin, "Mine")
    body = {"cycle_week": 1, "weekday": 0, "meal_type": "lunch", "price": 30, "dish_ids": [own]}
    for client in (clients.student, clients.operator, clients.provider):
        assert (await client.post("/dishes/meal-sets", json=body)).status_code == 403
        assert (await client.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})).status_code == 403
    assert (
        await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-03"})
    ).status_code == 422
    for changes in (
        {"dish_ids": [foreign]},
        {"dish_ids": [own, own]},
        {"dish_ids": []},
        {"price": 0},
        {"cycle_week": 3},
        {"weekday": 5},
        {"meal_type": "unknown"},
    ):
        assert (await clients.admin.post("/dishes/meal-sets", json={**body, **changes})).status_code in (400, 422)


async def test_edit_delete_are_scoped_and_replace_components(clients):
    first = await make_dish(clients.admin, "First")
    second = await make_dish(clients.admin, "Second")
    body = {"cycle_week": 1, "weekday": 0, "meal_type": "lunch", "price": 30, "dish_ids": [first, second]}
    assert (await clients.admin.post("/dishes/meal-sets", json=body)).status_code == 200
    meal_id = (await clients.admin.get("/dishes/meal-sets")).json()["sets"][0]["id"]
    assert (await clients.admin2.put(f"/dishes/meal-sets/{meal_id}", json=body)).status_code in (400, 404)
    assert (await clients.admin2.delete(f"/dishes/meal-sets/{meal_id}")).status_code == 404
    for client in (clients.student, clients.operator, clients.provider):
        assert (await client.put(f"/dishes/meal-sets/{meal_id}", json=body)).status_code == 403
        assert (await client.delete(f"/dishes/meal-sets/{meal_id}")).status_code == 403
    assert (
        await clients.admin.put(f"/dishes/meal-sets/{meal_id}", json={**body, "dish_ids": [second], "price": 40})
    ).status_code == 200
    meal = (await clients.admin.get("/dishes/meal-sets")).json()["sets"][0]
    assert meal["dish_ids"] == [second] and meal["price"] == 40
    assert (await clients.admin.delete(f"/dishes/meal-sets/{meal_id}")).status_code == 200
    assert (await clients.admin.get("/dishes/meal-sets")).json()["sets"] == []


async def test_student_menu_sums_components_and_never_leaks_catalog(clients, monkeypatch):
    monkeypatch.setattr("app.api.routers.dishes.menu_now", lambda: datetime(2026, 11, 2, 10, tzinfo=UTC))
    first = await make_dish(
        clients.admin, "Soup", serving_weight_g=100, energy_kcal=50, protein_g=2, fat_g=3, carbohydrates_g=4
    )
    second = await make_dish(
        clients.admin, "Tea", serving_weight_g=200, energy_kcal=30, protein_g=1, fat_g=0, carbohydrates_g=7
    )
    await make_dish(clients.admin, "Not offered")
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"] == []
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    body = {"cycle_week": 1, "weekday": 1, "meal_type": "lunch", "price": 80, "dish_ids": [first, second]}
    assert (await clients.admin.post("/dishes/meal-sets", json=body)).status_code == 200
    data = (await clients.student.get("/dishes/dishes_tomorrow")).json()
    assert data["pickup_date"] == "2026-11-03"
    assert data["dishes"] == []
    meal = data["sets"][0]
    assert [d["dish_name"] for d in meal["components"]] == ["Soup", "Tea"]
    assert [meal[k] for k in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")] == [
        300,
        80,
        3,
        3,
        11,
    ]
    assert "quantity" not in meal
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-09"})
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"] == []
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": None})
    assert (await clients.student.get("/dishes/dishes_tomorrow")).json()["sets"] == []


@pytest.mark.parametrize("current_day", [7, 8], ids=["saturday", "sunday"])
async def test_weekend_menu_only_contains_next_monday_sets(clients, monkeypatch, current_day):
    monkeypatch.setattr("app.api.routers.dishes.menu_now", lambda: datetime(2026, 11, current_day, 10, tzinfo=UTC))
    monday_dish = await make_dish(clients.admin, "Monday breakfast")
    other_dish = await make_dish(clients.admin, "Tuesday lunch")
    await make_dish(clients.admin, "Unoffered dish")
    assert (
        await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    ).status_code == 200
    monday = {"cycle_week": 2, "weekday": 0, "meal_type": "breakfast", "price": 50, "dish_ids": [monday_dish]}
    tuesday = {"cycle_week": 2, "weekday": 1, "meal_type": "lunch", "price": 70, "dish_ids": [other_dish]}
    assert (await clients.admin.post("/dishes/meal-sets", json=monday)).status_code == 200
    assert (await clients.admin.post("/dishes/meal-sets", json=tuesday)).status_code == 200
    assert (await clients.admin.post("/dishes/meal-sets", json={**monday, "weekday": 5})).status_code == 422
    assert (await clients.admin.post("/dishes/meal-sets", json={**monday, "weekday": 6})).status_code == 422
    menu = (await clients.student.get("/dishes/dishes_tomorrow")).json()
    assert menu["pickup_date"] == "2026-11-09"
    assert menu["dishes"] == []
    assert len(menu["sets"]) == 1
    assert menu["sets"][0]["weekday"] == 0
    assert menu["sets"][0]["dish_ids"] == [monday_dish]


async def test_friday_menu_targets_monday_of_second_week(clients, monkeypatch):
    monkeypatch.setattr("app.api.routers.dishes.menu_now", lambda: datetime(2026, 11, 6, 10, tzinfo=UTC))
    dish = await make_dish(clients.admin, "Monday")
    await clients.admin.put("/dishes/cycle-anchor", json={"cycle_start_monday": "2026-11-02"})
    body = {"cycle_week": 2, "weekday": 0, "meal_type": "breakfast", "price": 50, "dish_ids": [dish]}
    assert (await clients.admin.post("/dishes/meal-sets", json=body)).status_code == 200
    data = (await clients.student.get("/dishes/dishes_tomorrow")).json()
    assert data["pickup_date"] == "2026-11-09"
    assert len(data["sets"]) == 1 and data["sets"][0]["dish_ids"] == [dish]
