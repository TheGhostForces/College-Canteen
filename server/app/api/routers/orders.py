from datetime import date

import jwt
from fastapi import APIRouter, Response

from app.api.deps import CurrentStudent, Operator, OrdersRepo, Provider, UsersRepo
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
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
)

router = APIRouter(prefix="/orders", tags=["Заказы"])


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
    return OrderCreatedResponse(Order=OrderCreated(**await orders.create_from_basket(student.id)))


@router.delete("/order", response_model=OkResponse, summary="Отменить сегодняшний заказ (студент)")
async def cancel_order(student: CurrentStudent, orders: OrdersRepo):
    if now_local().hour >= get_settings().order_cancel_deadline_hour:
        raise BadRequestError("Not enough time")
    await orders.cancel_todays_order(student.id)
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
        Orders=await orders.get_student_orders(student.id, pickup_date=today_local()),
    )


@router.patch("/order", response_model=OkResponse, summary="Отметить заказ студента выданным (оператор)")
async def complete_order(body: PickupTokenRequest, operator: Operator, users: UsersRepo, orders: OrdersRepo):
    student = await _get_student_of_operator(body.pickup_token, operator, users)
    if not await orders.complete_todays_orders(student.id):
        raise NotFoundError("No order in progress for this student")
    return OkResponse()


@router.get("/orders_date", response_model=OrdersResponse, summary="Заказы заведения на день выдачи (оператор)")
async def get_orders_for_pickup_date(target_date: date, operator: Operator, orders: OrdersRepo):
    return OrdersResponse(Orders=await orders.get_institution_orders(operator.institution_id, target_date))


# ---- поставщик ----
@router.get("/total_quantity", response_model=OrderedDishesResponse, summary="Заказано на завтра (поставщик)")
async def get_ordered_totals(institution_id: int, provider: Provider, orders: OrdersRepo):
    return OrderedDishesResponse(dishes=await orders.get_ordered_totals(institution_id, tomorrow_local()))


@router.get("/orders", response_model=OrdersResponse, summary="Все активные заказы заведения (поставщик)")
async def get_institution_orders(institution_id: int, provider: Provider, orders: OrdersRepo):
    return OrdersResponse(Orders=await orders.get_institution_orders(institution_id))
