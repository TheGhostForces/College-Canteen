from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, Response

from app.api.deps import CurrentStudent, CurrentUser, Operator, OrdersRepo, Provider, UsersRepo
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.security import create_pickup_token, decode_pickup_token
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.models import StudentsOrm, UsersOrm
from app.schemas.common import OkResponse
from app.schemas.orders import (
    OrderCreated,
    OrderCreatedResponse,
    OrderedDishesResponse,
    OrdersResponse,
    PickupTokenRequest,
    PickupTokenResponse,
    StudentOrdersResponse,
    SupplierReportResponse,
)
from app.services.menu_calendar import next_pickup_day

router = APIRouter(prefix="/orders", tags=["Заказы"])


def pickup_now():
    return datetime.now(UTC)


@router.get("/next-pickup-date")
async def pickup_date(user: CurrentUser):
    if user.role not in ("provider", "operator"):
        raise ForbiddenError("Insufficient permissions")
    return {"pickup_date": next_pickup_day(pickup_now(), ZoneInfo(get_settings().timezone))}


def ensure_provider_institution(provider: UsersOrm, institution_id: int) -> None:
    if provider.institution_id != institution_id:
        raise ForbiddenError("Insufficient permissions")


async def _get_student_of_operator(token: str, operator: UsersOrm, users: UsersRepo) -> StudentsOrm:
    """Проверяем QR и актуальную принадлежность студента заведению оператора."""
    try:
        claims = decode_pickup_token(token)
    except (jwt.PyJWTError, ValueError):
        raise BadRequestError("Pickup token has expired or is invalid") from None
    student = await users.get_student_by_id(claims["student_id"])
    if (
        student is None
        or student.user_id != int(claims["sub"])
        or claims["institution_id"] != operator.institution_id
        or await users.get_student_institution_id(student.id) != operator.institution_id
    ):
        raise NotFoundError("Student not found")
    user = await users.get_by_id(student.user_id)
    if user is None or user.role != "student":
        raise NotFoundError("Student not found")
    return student


# ---- студент ----
@router.post("/order", response_model=OrderCreatedResponse, summary="Оформить заказ из корзины (студент)")
async def create_order(student: CurrentStudent, orders: OrdersRepo):
    return OrderCreatedResponse(Order=OrderCreated(**await orders.create_from_basket(student.id, allow_legacy=False)))


@router.delete("/order", response_model=OkResponse, summary="Отменить сегодняшний заказ (студент)")
async def cancel_order(student: CurrentStudent, orders: OrdersRepo):
    await orders.cancel_todays_order(student.id, legacy_now=now_local())
    return OkResponse()


@router.get("/order", response_model=StudentOrdersResponse, summary="Мои активные заказы (студент)")
async def get_my_orders(student: CurrentStudent, orders: OrdersRepo):
    return StudentOrdersResponse(
        Name=student.full_name, Student_ID=student.id, Orders=await orders.get_student_orders(student.id)
    )


@router.post("/pickup_token", response_model=PickupTokenResponse, summary="Получить QR для выдачи (студент)")
async def get_pickup_token(student: CurrentStudent, users: UsersRepo, response: Response):
    institution_id = await users.get_student_institution_id(student.id)
    if institution_id is None:
        raise NotFoundError("Student institution not found")
    token, expires_at = create_pickup_token(student.user_id, student.id, institution_id)
    response.headers["Cache-Control"] = "no-store"
    return PickupTokenResponse(pickup_token=token, expires_at=expires_at)


# ---- оператор раздачи ----
@router.post(
    "/student_order",
    response_model=StudentOrdersResponse,
    summary="Заказы студента к выдаче сегодня (оператор)",
)
async def get_student_orders_for_pickup(
    body: PickupTokenRequest, operator: Operator, users: UsersRepo, orders: OrdersRepo
):
    student = await _get_student_of_operator(body.pickup_token, operator, users)
    return StudentOrdersResponse(
        Name=student.full_name,
        Student_ID=student.id,
        Orders=await orders.get_student_orders(
            student.id, pickup_date=today_local(), institution_id=operator.institution_id
        ),
    )


@router.patch("/order", response_model=OkResponse, summary="Отметить заказ студента выданным (оператор)")
async def complete_order(body: PickupTokenRequest, operator: Operator, users: UsersRepo, orders: OrdersRepo):
    student = await _get_student_of_operator(body.pickup_token, operator, users)
    if not await orders.complete_todays_orders(student.id, operator.institution_id):
        raise NotFoundError("No order in progress for this student")
    return OkResponse()


@router.get("/orders_date", response_model=OrdersResponse, summary="Заказы заведения на день выдачи (оператор)")
async def get_orders_for_pickup_date(target_date: date, operator: Operator, orders: OrdersRepo):
    return OrdersResponse(Orders=await orders.get_institution_orders(operator.institution_id, target_date))


# ---- поставщик ----
@router.get("/supplier-report", response_model=SupplierReportResponse, summary="Сводка заказов (поставщик)")
async def supplier_report(institution_id: int, target_date: date, provider: Provider, orders: OrdersRepo):
    ensure_provider_institution(provider, institution_id)
    return SupplierReportResponse(**await orders.get_supplier_report(institution_id, target_date))


@router.get("/total_quantity", response_model=OrderedDishesResponse, summary="Заказано на завтра (поставщик)")
async def get_ordered_totals(institution_id: int, provider: Provider, orders: OrdersRepo):
    ensure_provider_institution(provider, institution_id)
    return OrderedDishesResponse(dishes=await orders.get_ordered_totals(institution_id, tomorrow_local()))


@router.get("/orders", response_model=OrdersResponse, summary="Все активные заказы заведения (поставщик)")
async def get_institution_orders(
    institution_id: int, provider: Provider, orders: OrdersRepo, target_date: date | None = None
):
    ensure_provider_institution(provider, institution_id)
    return OrdersResponse(Orders=await orders.get_institution_orders(institution_id, target_date))
