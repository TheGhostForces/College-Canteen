"""Task 5 checks; normal pytest also runs the shared PostgreSQL fixtures."""

import os
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# These placeholders only allow importing the app; this test never connects to a database.
if os.environ.get("CANTEEN_TEST_PGPASS", "").lower() not in ("1", "true", "yes", "on"):
    os.environ.setdefault("POSTGRES_PASSWORD", "unused")
os.environ.setdefault("SECRET_KEY", "unused-test-key-that-is-long-enough")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.api.routers.dishes import set_plan_for_day  # noqa: E402
from app.core.exceptions import ForbiddenError  # noqa: E402
from app.core.timeutils import today_local  # noqa: E402
from app.repositories.orders import OrdersRepository  # noqa: E402
from app.schemas.dishes import DishPlan  # noqa: E402


def test_pgpass_requires_explicit_test_opt_in_and_authorized_target(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("CANTEEN_TEST_PGPASS", raising=False)
    args = {"secret_key": "x" * 32, "_env_file": None}
    with pytest.raises(ValidationError):
        Settings(**args)
    settings = Settings(**args, canteen_test_pgpass=True, postgres_db="test")
    assert settings.database_url.password is None
    with pytest.raises(ValidationError):
        Settings(**args, canteen_test_pgpass=True, postgres_db="other")
    with pytest.raises(ValidationError):
        Settings(**args, canteen_test_pgpass=True, postgres_db="test", postgres_password="unused")
    ordinary = Settings(**args, postgres_password="unused")
    assert ordinary.database_url.password == "unused"


def test_config_validation_error_does_not_render_secrets(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.delenv("CANTEEN_TEST_PGPASS", raising=False)
    password = "secret-password-marker-0987"
    secret_key = "secret-key-marker-0123456789-0123456789"
    api_key = "secret-api-marker-0293"
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None, postgres_db="test", canteen_test_pgpass=True,
            postgres_password=password, secret_key=secret_key, resend_api_key=api_key,
        )
    def assert_redacted(error):
        for rendered in (str(error), repr(error), error.json(), repr(error.errors())):
            for secret in (password, secret_key, api_key):
                assert secret not in rendered

    assert_redacted(caught.value)
    with pytest.raises(ValidationError) as missing_password:
        Settings(_env_file=None, secret_key=secret_key, resend_api_key=api_key)
    assert_redacted(missing_password.value)
    with pytest.raises(ValidationError) as invalid_key:
        Settings(_env_file=None, postgres_password=password, secret_key="short-secret-marker")
    for rendered in (
        str(invalid_key.value), repr(invalid_key.value), invalid_key.value.json(), repr(invalid_key.value.errors())
    ):
        assert "short-secret-marker" not in rendered


@pytest.mark.asyncio
async def test_supplier_cannot_modify_daily_plan():
    repository = SimpleNamespace(set_plan_for_day=AsyncMock())
    with pytest.raises(ForbiddenError):
        await set_plan_for_day(1, DishPlan(items=[]), today_local() + timedelta(days=1), object(), repository)
    repository.set_plan_for_day.assert_not_awaited()


def test_supplier_and_operator_pages_expose_new_workflows():
    root = Path(__file__).resolve().parents[2] / "frontend"
    supplier = (root / "food_supplier/meal_planning.html").read_text()
    operator = (root / "distribution_operator/dishes_tomorrow.html").read_text()
    assert "/api/orders/supplier-report?" in supplier
    assert "/api/dishes/dishes?" not in supplier
    assert "/api/dishes/buffet" in operator
    assert 'id="buffet_container"' in operator
    assert "/api/orders/orders_date?" in operator


@pytest.mark.asyncio
async def test_operator_catalog_is_scoped_to_their_institution():
    from app.api.routers.dishes import buffet_catalog

    repo = SimpleNamespace(get_active=AsyncMock(return_value=[SimpleNamespace(id=9, dish_name="Tea")]))
    result = await buffet_catalog(SimpleNamespace(institution_id=7), repo)
    assert result == {"dishes": [{"id": 9, "dish_name": "Tea"}]}
    repo.get_active.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_operator_can_change_stock_but_not_sets():
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user
    from app.main import app

    user = SimpleNamespace(role="operator", institution_id=7)
    dish = SimpleNamespace(id=2, institution_id=7, dish_name="Tea", category="Drinks", fixed_price=10,
                           img_url=None, serving_weight_g=0, energy_kcal=0, protein_g=0, fat_g=0, carbohydrates_g=0)
    offering = SimpleNamespace(id=3, dish=dish, quantity=4, is_visible=False)
    repo = SimpleNamespace(update_buffet=AsyncMock(return_value=offering), buffet=AsyncMock(return_value=[offering]))
    app.dependency_overrides[get_current_user] = lambda: user
    for route in app.routes:
        if getattr(route, "path", "").startswith("/dishes/"):
            for dep in route.dependant.dependencies:
                if dep.name == "dishes":
                    app.dependency_overrides[dep.call] = lambda: repo
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listing = await client.get("/dishes/buffet")
            assert listing.status_code == 200
            assert listing.json()["offerings"][0]["quantity"] == 4
            assert listing.json()["offerings"][0]["is_visible"] is False
            response = await client.patch("/dishes/buffet/3", json={"delta": -2, "is_visible": False})
            assert response.status_code == 200
            repo.update_buffet.assert_awaited_once_with(7, 3, -2, False)
            response = await client.post("/dishes/meal-sets", json={
                "cycle_week": 1, "weekday": 0, "meal_type": "lunch", "price": 100, "dish_ids": [2]
            })
            assert response.status_code == 403
            user.role = "provider"
            response = await client.put("/dishes/dishes?institution_id=7&target_date=2030-01-01", json={"items": []})
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_report_requires_provider_role_over_http():
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_current_user
    from app.main import app

    user = SimpleNamespace(role="provider", institution_id=1)
    repo = SimpleNamespace(get_supplier_report=AsyncMock(return_value={"sets": [], "buffet": []}))
    route = next(r for r in app.routes if getattr(r, "path", "") == "/orders/supplier-report")
    dependency = next(dep.call for dep in route.dependant.dependencies if dep.name == "orders")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[dependency] = lambda: repo
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            url = "/orders/supplier-report?institution_id=2&target_date=2026-11-05"
            assert (await client.get(url)).status_code == 403
            repo.get_supplier_report.assert_not_awaited()
            url = "/orders/supplier-report?institution_id=1&target_date=2026-11-05"
            assert (await client.get(url)).status_code == 200
            repo.get_supplier_report.assert_awaited_once_with(1, date(2026, 11, 5))
            user.role = "operator"
            assert (await client.get(url)).status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_supplier_report_endpoint_passes_institution_and_date():
    from app.api.routers.orders import supplier_report

    repo = SimpleNamespace(get_supplier_report=AsyncMock(return_value={"sets": [], "buffet": []}))
    result = await supplier_report(7, date(2026, 11, 5), SimpleNamespace(institution_id=7), repo)
    assert result.sets == [] and result.buffet == []
    repo.get_supplier_report.assert_awaited_once_with(7, date(2026, 11, 5))


@pytest.mark.asyncio
async def test_supplier_report_groups_and_filters_order_lines():
    # SQLite in memory is disposable and exercises the actual query without PostgreSQL credentials.
    engine = create_engine("sqlite://")
    with Session(engine) as session:
        session.execute(text('CREATE TABLE "Order" (id INTEGER PRIMARY KEY, institution_id INTEGER, '
                             'pickup_date DATE, order_status VARCHAR)'))
        session.execute(text('CREATE TABLE "TypedOrderItem" (id INTEGER PRIMARY KEY, order_id INTEGER, '
                             'buffet_offering_id INTEGER, meal_set_id INTEGER, item_type VARCHAR, meal_type VARCHAR, '
                             'quantity INTEGER, unit_price INTEGER, snapshot JSON)'))
        session.execute(text('INSERT INTO "Order" VALUES '
                             "(1, 1, '2026-11-05', 'IN_PROGRESS'), (2, 1, '2026-11-05', 'COMPLETED'), "
                             "(3, 1, '2026-11-05', 'CANCELLED'), (4, 2, '2026-11-05', 'IN_PROGRESS'), "
                             "(5, 1, '2026-11-06', 'IN_PROGRESS')"))
        session.execute(text('INSERT INTO "TypedOrderItem" VALUES '
                             "(1, 1, NULL, 10, 'set', 'lunch', 1, 100, '{}'), "
                             "(2, 2, NULL, 10, 'set', 'lunch', 1, 100, '{\"components\":[{\"dish_name\":\"New\"}]}'), "
                             "(3, 1, 20, NULL, 'buffet', NULL, 2, 10, '{\"dish_name\":\"Tea\"}'), "
                             "(4, 2, 20, NULL, 'buffet', NULL, 1, 10, '{\"dish_name\":\"Tea\"}'), "
                             "(5, 3, 20, NULL, 'buffet', NULL, 99, 10, '{}'), "
                             "(6, 4, 20, NULL, 'buffet', NULL, 99, 10, '{}'), "
                             "(7, 5, 20, NULL, 'buffet', NULL, 99, 10, '{}'), "
                             "(8, 1, NULL, 11, 'set', 'breakfast', 1, 100, '{}'), "
                             "(9, 1, 21, NULL, 'buffet', NULL, 4, 10, '{\"dish_name\":\"Cake\"}')"))

        class AsyncSessionAdapter:
            async def execute(self, statement):
                return session.execute(statement)

        repo = OrdersRepository(AsyncSessionAdapter())
        report = await repo.get_supplier_report(1, date(2026, 11, 5))
        assert report == {
            "sets": [
                {"meal_set_id": 10, "meal_type": "lunch", "quantity": 1, "components": []},
                {"meal_set_id": 10, "meal_type": "lunch", "quantity": 1, "components": [{"dish_name": "New"}]},
                {"meal_set_id": 11, "meal_type": "breakfast", "quantity": 1, "components": []},
            ],
            "buffet": [
                {"buffet_offering_id": 20, "dish_name": "Tea", "quantity": 3},
                {"buffet_offering_id": 21, "dish_name": "Cake", "quantity": 4},
            ],
        }
        assert await repo.get_supplier_report(1, date(2026, 11, 7)) == {"sets": [], "buffet": []}
        assert (await repo.get_supplier_report(2, date(2026, 11, 5)))["buffet"][0]["quantity"] == 99
        assert (await repo.get_supplier_report(1, date(2026, 11, 6)))["buffet"][0]["quantity"] == 99
