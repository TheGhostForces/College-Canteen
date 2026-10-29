"""Тесты идут на настоящем PostgreSQL (схема создаётся миграциями Alembic).

Подключение берётся из POSTGRES_* (по умолчанию localhost, БД canteen_test, создаётся автоматически).
"""

import asyncio
import os
from datetime import date

os.environ.setdefault("POSTGRES_DB", "canteen_test")
os.environ.setdefault("POSTGRES_PASSWORD", "postgres")
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")
os.environ["COOKIE_SECURE"] = "false"
os.environ["ENABLE_DOCS"] = "false"

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.timeutils import tomorrow_local  # noqa: E402
from app.db import models  # noqa: E402
from app.db.session import SessionFactory  # noqa: E402
from app.main import app  # noqa: E402
from app.services import mailer  # noqa: E402,F401

SETTINGS = get_settings()
TABLES = [
    "OrderDish",
    "Order",
    "ShoppingCartDishes",
    "ShoppingCart",
    "ScheduleDishes",
    "Dishes",
    "TemporaryCode",
    "Students",
    "Users",
    "EducationInstitution",
]


def _admin_dsn(database: str) -> dict:
    return dict(
        user=SETTINGS.postgres_user,
        password=SETTINGS.postgres_password.get_secret_value(),
        host=SETTINGS.postgres_host,
        port=SETTINGS.postgres_port,
        database=database,
    )


async def _ensure_database() -> None:
    conn = await asyncpg.connect(**_admin_dsn("postgres"))
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", SETTINGS.postgres_db)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{SETTINGS.postgres_db}"')
    finally:
        await conn.close()


async def _truncate() -> None:
    conn = await asyncpg.connect(**_admin_dsn(SETTINGS.postgres_db))
    try:
        names = ", ".join(f'"{t}"' for t in TABLES)
        await conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


@pytest.fixture(scope="session", autouse=True)
def database():
    asyncio.run(_ensure_database())
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean_tables(database):
    asyncio.run(_truncate())


@pytest.fixture
def sent_codes(monkeypatch) -> dict[str, str]:
    """Вместо реальной отправки письма запоминаем код: {email: code}."""
    codes: dict[str, str] = {}
    monkeypatch.setattr("app.api.routers.auth.send_login_code", lambda email, code: codes.update({email.lower(): code}))
    return codes


class World:
    """Тестовые данные: два заведения и по одному пользователю каждой роли."""

    inst1: int
    inst2: int


@pytest.fixture
async def world() -> World:
    w = World()
    async with SessionFactory() as s:
        i1, i2 = models.EducationInstitutionOrm(name="College 1"), models.EducationInstitutionOrm(name="College 2")
        s.add_all([i1, i2])
        await s.flush()
        w.inst1, w.inst2 = i1.id, i2.id

        def student(email, inst):
            user = models.UsersOrm(email=email, role="student", institution_id=inst)
            user.student = models.StudentsOrm(
                full_name=f"Student {email}", group_name="G-1", date_start=date(2024, 1, 1), date_end=date(2030, 1, 1)
            )
            return user

        s.add_all(
            [
                student("stud@x.ru", i1.id),
                student("stud2@x.ru", i1.id),
                models.UsersOrm(email="admin@x.ru", role="admin", institution_id=i1.id),
                models.UsersOrm(email="admin2@x.ru", role="admin", institution_id=i2.id),
                models.UsersOrm(email="prov@x.ru", role="provider", institution_id=i1.id),
                models.UsersOrm(email="op@x.ru", role="operator", institution_id=i1.id),
                models.UsersOrm(email="op2@x.ru", role="operator", institution_id=i2.id),
            ]
        )
        await s.commit()
    return w


def _new_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
async def anon():
    async with _new_client() as c:
        yield c


@pytest.fixture
async def login(sent_codes, world):
    """login("stud@x.ru") -> авторизованный клиент (cookie сохраняется в клиенте)."""
    clients: list[AsyncClient] = []

    async def _login(email: str) -> AsyncClient:
        client = _new_client()
        clients.append(client)
        r = await client.post("/auth/generate", json={"email": email})
        assert r.status_code == 200, r.text
        data = r.json()
        r = await client.post(
            "/auth/confirm",
            json={
                "user_id": data["user_id"],
                "temporary_code_id": data["tmp_code_id"],
                "code": sent_codes[email.lower()],
            },
        )
        assert r.status_code == 200, r.text
        return client

    yield _login
    for client in clients:
        await client.aclose()


@pytest.fixture
async def clients(login):
    """Все роли сразу: clients.student, .student2, .admin, .admin2, .provider, .operator, .operator2"""

    class Clients:
        pass

    c = Clients()
    c.student = await login("stud@x.ru")
    c.student2 = await login("stud2@x.ru")
    c.admin = await login("admin@x.ru")
    c.admin2 = await login("admin2@x.ru")
    c.provider = await login("prov@x.ru")
    c.operator = await login("op@x.ru")
    c.operator2 = await login("op2@x.ru")
    return c


@pytest.fixture
async def menu(clients, world):
    """Меню заведения 1: два блюда, на завтра запланировано 5 порций борща и 3 чая."""
    r = await clients.admin.post(
        "/dishes/dish",
        json={
            "items": [
                {"dish_name": "Борщ", "category": "Первое", "fixed_price": 100},
                {"dish_name": "Чай", "category": "Напитки", "fixed_price": 20},
            ]
        },
    )
    assert r.status_code == 200, r.text
    soup, tea = r.json()["Result"]["created_dish_ids"]
    r = await clients.provider.put(
        "/dishes/dishes",
        params={"institution_id": world.inst1, "target_date": tomorrow_local().isoformat()},
        json={"items": [{"dish_id": soup, "cart_quantity": 5}, {"dish_id": tea, "cart_quantity": 3}]},
    )
    assert r.status_code == 200, r.text
    return {"soup": soup, "tea": tea}
