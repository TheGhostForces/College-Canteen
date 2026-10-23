from datetime import date

from fastapi import APIRouter

from app.api.deps import CurrentStudent, Operator, OrdersRepo, Provider, UsersRepo
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.models import StudentsOrm, UsersOrm
from app.schemas.common import OkResponse
from app.schemas.orders import (
    OrderCreated,
    OrderCreatedResponse,
    OrderedDishesResponse,
    OrdersResponse,
    StudentOrdersResponse,
)

router = APIRouter(prefix="/orders", tags=["Заказы"])


async def _get_student_of_operator(student_id: int, operator: UsersOrm, users: UsersRepo) -> StudentsOrm:
    """Оператор работает только со студентами своего заведения (чужих "не видит")."""
    student = await users.get_student_by_id(student_id)
    if student is None or await users.get_student_institution_id(student_id) != operator.institution_id:
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


# ---- оператор раздачи ----
@router.get(
    "/student_order",
    response_model=StudentOrdersResponse,
    summary="Заказы студента к выдаче сегодня (оператор)",
)
async def get_student_orders_for_pickup(student_id: int, operator: Operator, users: UsersRepo, orders: OrdersRepo):
    student = await _get_student_of_operator(student_id, operator, users)
    return StudentOrdersResponse(
        Name=student.full_name,
        Student_ID=student.id,
        Orders=await orders.get_student_orders(student.id, pickup_date=today_local()),
    )


@router.patch("/order", response_model=OkResponse, summary="Отметить заказ студента выданным (оператор)")
async def complete_order(student_id: int, operator: Operator, users: UsersRepo, orders: OrdersRepo):
    await _get_student_of_operator(student_id, operator, users)
    if not await orders.complete_todays_orders(student_id):
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
