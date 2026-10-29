from datetime import date

import pytest
from sqlalchemy import func, select

from app.bootstrap_admin import bootstrap_admin
from app.db.models import DishesOrm, EducationInstitutionOrm, StudentsOrm, UsersOrm
from app.db.session import SessionFactory

STUDENT = {
    "full_name": "Иван Иванов",
    "group_name": "ИС-21",
    "date_start": "2024-09-01",
    "date_end": "2028-06-30",
}


def user_body(role="operator", email="new@example.ru", **extra):
    return {"user": {"email": email, "role": role, **extra}}


@pytest.mark.parametrize("path", ["/admin/me", "/admin/users", "/admin/dishes"])
async def test_anonymous_cannot_read(anon, path):
    response = await anon.get(path)
    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"


async def test_anonymous_cannot_create(anon):
    assert (await anon.post("/admin/user", json=user_body())).status_code == 401


@pytest.mark.parametrize("role", ["student", "provider", "operator"])
async def test_non_admin_denied(clients, role):
    client = getattr(clients, role)
    for path in ("/admin/me", "/admin/users", "/admin/dishes"):
        assert (await client.get(path)).status_code == 403
    assert (await client.post("/admin/user", json=user_body())).status_code == 403
    body = {"items": [{"dish_name": "Чужое блюдо", "category": "Первое", "fixed_price": 10}]}
    assert (await client.post("/dishes/dish", json=body)).status_code == 403
    assert (await client.patch("/dishes/dish?dish_id=1", json={"fixed_price": 20})).status_code == 403
    assert (await client.delete("/dishes/dish?dish_ids=1")).status_code == 403


async def test_me_and_users_are_scoped_and_paginated(clients, world):
    me = (await clients.admin.get("/admin/me")).json()
    assert me["email"] == "admin@x.ru"
    assert me["institution"] == {"id": world.inst1, "name": "College 1"}
    response = await clients.admin.get("/admin/users", params={"limit": 2, "offset": 0})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    first = response.json()
    assert first["total"] == 5
    assert first["limit"] == 2 and first["offset"] == 0
    assert len(first["users"]) == 2
    assert first["users"][0]["student"]["group_name"] == "G-1"
    second = (await clients.admin.get("/admin/users?limit=2&offset=2")).json()
    assert {u["id"] for u in first["users"]}.isdisjoint(u["id"] for u in second["users"])
    own = (await clients.admin.get("/admin/users", params={"institution_id": world.inst2})).json()["users"]
    assert len(own) == 5
    assert all(u["institution_id"] == world.inst1 for u in own)
    other = (await clients.admin2.get("/admin/users")).json()
    assert other["total"] == 2
    assert all(u["institution_id"] == world.inst2 for u in other["users"])
    assert (await clients.admin.get("/admin/users?offset=999")).json()["users"] == []


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
async def test_pagination_validation(clients, query):
    assert (await clients.admin.get(f"/admin/users?{query}")).status_code == 422


@pytest.mark.parametrize("role", ["student", "provider", "operator"])
async def test_create_only_in_own_institution(clients, world, role):
    body = user_body(role, "NEW@example.ru", institution_id=world.inst2)
    if role == "student":
        body["student"] = STUDENT
    response = await clients.admin.post("/admin/user", json=body)
    assert response.status_code == 200, response.text
    user_id = response.json()["user_id"]
    async with SessionFactory() as session:
        user = await session.get(UsersOrm, user_id)
        assert user.email == "new@example.ru"
        assert user.role == role
        assert user.institution_id == world.inst1
        profile = await session.scalar(select(StudentsOrm).where(StudentsOrm.user_id == user_id))
        if role == "student":
            assert profile.full_name == STUDENT["full_name"]
            assert profile.group_name == STUDENT["group_name"]
            assert profile.date_start == date(2024, 9, 1)
            assert profile.date_end == date(2028, 6, 30)
        else:
            assert profile is None
    own = (await clients.admin.get("/admin/users")).json()["users"]
    assert any(u["id"] == user_id for u in own)
    other = (await clients.admin2.get("/admin/users")).json()["users"]
    assert all(u["id"] != user_id for u in other)


async def test_create_without_institution_and_student_can_login(clients, login, world):
    body = user_body("student", "fresh@example.ru")
    body["student"] = STUDENT
    response = await clients.admin2.post("/admin/user", json=body)
    assert response.status_code == 200, response.text
    client = await login("fresh@example.ru")
    assert (await client.get("/dishes/dishes_tomorrow")).status_code == 200
    assert (await client.get("/admin/users")).status_code == 403
    async with SessionFactory() as session:
        user = await session.get(UsersOrm, response.json()["user_id"])
        assert user.institution_id == world.inst2


async def test_admin_creation_is_forbidden_and_existing_email_unchanged(clients):
    for email in ("new-admin@example.ru", "stud@x.ru"):
        response = await clients.admin.post("/admin/user", json=user_body("admin", email))
        assert response.status_code == 422
    async with SessionFactory() as session:
        assert await session.scalar(select(UsersOrm).where(UsersOrm.email == "new-admin@example.ru")) is None
        student = await session.scalar(select(UsersOrm).where(UsersOrm.email == "stud@x.ru"))
        assert student.role == "student"


async def test_missing_or_invalid_student_does_not_create_user(clients):
    response = await clients.admin.post("/admin/user", json=user_body("student"))
    assert response.status_code == 400
    for changes in ({"date_end": "2020-01-01"}, {"full_name": "  "}, {"group_name": "  "}):
        body = user_body("student")
        body["student"] = {**STUDENT, **changes}
        assert (await clients.admin.post("/admin/user", json=body)).status_code == 422
    body = user_body()
    body["student"] = STUDENT
    assert (await clients.admin.post("/admin/user", json=body)).status_code == 400
    async with SessionFactory() as session:
        assert await session.scalar(select(UsersOrm.id).where(UsersOrm.email == "new@example.ru")) is None


async def test_duplicate_email_is_case_insensitive_and_scoped_data_unchanged(clients, world):
    response = await clients.admin2.post("/admin/user", json=user_body("provider", "STUD@x.ru"))
    assert response.status_code == 409
    async with SessionFactory() as session:
        user = await session.scalar(select(UsersOrm).where(UsersOrm.email == "stud@x.ru"))
        assert user.role == "student" and user.institution_id == world.inst1


async def test_dish_list_edit_and_soft_delete_are_isolated(clients, world):
    assert (await clients.admin.get("/admin/dishes")).json()["dishes"] == []
    body = {"items": [{"dish_name": "Суп", "category": "Первое", "fixed_price": 50}]}
    created = await clients.admin.post("/dishes/dish", json=body)
    dish_id = created.json()["Result"]["created_dish_ids"][0]
    own = (await clients.admin.get("/admin/dishes")).json()["dishes"]
    assert [d["id"] for d in own] == [dish_id]
    assert (await clients.admin2.get("/admin/dishes")).json()["dishes"] == []
    assert (await clients.admin2.get("/dishes/dish?name=Суп")).status_code == 404
    assert (await clients.admin2.patch(f"/dishes/dish?dish_id={dish_id}", json={"fixed_price": 1})).status_code == 404
    assert (await clients.admin2.delete(f"/dishes/dish?dish_ids={dish_id}")).status_code == 404
    response = await clients.admin.patch(
        f"/dishes/dish?dish_id={dish_id}&institution_id={world.inst2}", json={"fixed_price": 1}
    )
    assert response.status_code == 403
    assert (await clients.admin.patch(f"/dishes/dish?dish_id={dish_id}", json={"fixed_price": 60})).status_code == 200
    assert (await clients.admin.delete(f"/dishes/dish?dish_ids={dish_id}")).status_code == 200
    assert (await clients.admin.get("/admin/dishes")).json()["dishes"] == []
    async with SessionFactory() as session:
        dish = await session.get(DishesOrm, dish_id)
        assert dish is not None and not dish.is_active and dish.fixed_price == 60
        assert dish.institution_id == world.inst1


async def test_bootstrap_creates_only_admin_and_institution():
    async with SessionFactory() as session:
        user_id, institution_id = await bootstrap_admin(session, "ADMIN@example.ru", "  Новый колледж  ")
        user = await session.get(UsersOrm, user_id)
        assert user.email == "admin@example.ru" and user.role == "admin"
        assert user.institution_id == institution_id
        assert (await session.get(EducationInstitutionOrm, institution_id)).name == "Новый колледж"
        assert await session.scalar(select(func.count()).select_from(StudentsOrm)) == 0
        assert await session.scalar(select(func.count()).select_from(DishesOrm)) == 0
    async with SessionFactory() as session:
        _, reused = await bootstrap_admin(session, "second@example.ru", "Новый колледж")
        assert reused == institution_id


@pytest.mark.parametrize("email", ["STUD@x.ru", "ADMIN@x.ru", "admin2@x.ru"])
async def test_bootstrap_existing_email_never_promotes_or_moves(world, email):
    async with SessionFactory() as session:
        user = await session.scalar(select(UsersOrm).where(func.lower(UsersOrm.email) == email.lower()))
        original = user.id, user.role, user.institution_id
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="Email уже существует"):
            await bootstrap_admin(session, email, "Не создавать это учреждение")
    async with SessionFactory() as session:
        user = await session.get(UsersOrm, original[0])
        assert (user.id, user.role, user.institution_id) == original
        assert (
            await session.scalar(
                select(EducationInstitutionOrm.id).where(EducationInstitutionOrm.name == "Не создавать это учреждение")
            )
            is None
        )


async def test_bootstrap_existing_institution_id(world):
    async with SessionFactory() as session:
        user_id, institution_id = await bootstrap_admin(session, "by-id@example.ru", institution_id=world.inst2)
        assert institution_id == world.inst2
        user = await session.get(UsersOrm, user_id)
        assert user.role == "admin" and user.institution_id == world.inst2
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="не найдено"):
            await bootstrap_admin(session, "missing@example.ru", institution_id=999999)
    async with SessionFactory() as session:
        with pytest.raises(ValueError, match="не совпадает"):
            await bootstrap_admin(session, "mismatch@example.ru", "Wrong name", institution_id=world.inst1)


@pytest.mark.parametrize("flags", [[], ["--email", "admin@example.ru", "--institution-name", "Колледж"]])
def test_bootstrap_cli_arguments_and_interactive(monkeypatch, capsys, flags):
    import importlib

    cli = importlib.import_module("app.bootstrap_admin")
    captured = []
    answers = iter(["admin@example.ru", "Колледж"])

    async def fake_run(email, name, institution_id):
        captured.append((email, name, institution_id))
        return 10, 20

    monkeypatch.setattr("sys.argv", ["bootstrap_admin", *flags])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setattr(cli, "_run", fake_run)
    cli.main()
    assert captured == [("admin@example.ru", "Колледж", None)]
    assert "Администратор создан" in capsys.readouterr().out


async def test_bootstrap_rolls_back_institution_on_insert_failure(monkeypatch):
    from sqlalchemy.exc import IntegrityError

    async with SessionFactory() as session:
        flush = session.flush
        calls = 0

        async def fail_second_flush(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise IntegrityError("insert", {}, Exception("conflict"))
            return await flush(*args, **kwargs)

        monkeypatch.setattr(session, "flush", fail_second_flush)
        with pytest.raises(ValueError, match="Изменения отменены"):
            await bootstrap_admin(session, "new@example.ru", "Откат учреждения")
    async with SessionFactory() as session:
        assert await session.scalar(select(func.count()).select_from(EducationInstitutionOrm)) == 0
        assert await session.scalar(select(func.count()).select_from(UsersOrm)) == 0
