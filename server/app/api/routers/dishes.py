from datetime import date, timedelta

from fastapi import APIRouter, Query

from app.api.deps import Admin, DishesRepo, Operator, Provider, StudentUser
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.core.timeutils import today_local, tomorrow_local
from app.schemas.common import OkResponse
from app.schemas.dishes import (
    CreateDishesResponse,
    DeleteDishesResponse,
    DishCreateList,
    DishListResponse,
    DishPlan,
    DishResponse,
    DishScheduleListResponse,
    DishTomorrowResponse,
    DishUpdate,
    DishWithQuantityListResponse,
)

router = APIRouter(prefix="/dishes", tags=["Блюда"])

MAX_PLANNING_DAYS = 7


# ---- администратор: справочник блюд своего заведения ----
@router.get("/dish", response_model=DishResponse, summary="Блюдо по названию (админ)")
async def get_dish_by_name(name: str, admin: Admin, dishes: DishesRepo):
    name = name.strip()
    if not name:
        raise BadRequestError("Dish name cannot be empty")
    dish = await dishes.get_by_name(admin.institution_id, name)
    if dish is None:
        raise NotFoundError("Dish not found")
    return DishResponse(dish=dish)


@router.post("/dish", response_model=CreateDishesResponse, summary="Добавить блюда (админ)")
async def create_dishes(data: DishCreateList, admin: Admin, dishes: DishesRepo):
    return CreateDishesResponse(Result=await dishes.create_many(admin.institution_id, data))


@router.patch("/dish", response_model=OkResponse, summary="Изменить блюдо (админ)")
async def update_dish(
    data: DishUpdate,
    admin: Admin,
    dishes: DishesRepo,
    dish_id: int | None = None,
    dish_name: str | None = None,
    institution_id: int | None = None,
):
    # админ редактирует только блюда своего заведения
    if institution_id is not None and institution_id != admin.institution_id:
        raise ForbiddenError("Insufficient permissions")
    if dish_id is None and dish_name is None:
        raise BadRequestError("Cannot be updated without parameters")

    if dish_id is not None:
        dish = await dishes.get_by_id(dish_id)
    else:
        dish = await dishes.get_by_name(admin.institution_id, dish_name)
    if dish is None or dish.institution_id != admin.institution_id:
        raise NotFoundError("Dish not found")
    await dishes.update(dish.id, data)
    return OkResponse()


@router.delete("/dish", response_model=DeleteDishesResponse, summary="Убрать блюда из меню (админ)")
async def delete_dishes(
    admin: Admin,
    dishes: DishesRepo,
    dish_ids: list[int] | None = Query(None),
    dish_names: list[str] | None = Query(None),
):
    if not dish_ids and not dish_names:
        raise BadRequestError("Dish ids or names cannot be empty")

    deleted, not_found_ids, not_found_names = await dishes.deactivate(admin.institution_id, dish_ids, dish_names)

    not_found: dict = {}
    if not_found_ids:
        not_found["dish_ids"] = not_found_ids
    if not_found_names:
        not_found["dish_names"] = not_found_names

    if deleted == 0:
        raise NotFoundError(
            {"deleted_count": 0, "not_found": not_found} if not_found else "No dishes found matching the criteria"
        )
    return DeleteDishesResponse(
        data={"deleted_count": deleted, "not_found": not_found},
        message=f"Successfully deleted {deleted} dish(es)",
    )


# ---- студент ----
@router.get("/dishes_tomorrow", response_model=DishTomorrowResponse, summary="Меню на завтра (студент)")
async def get_menu_for_tomorrow(student: StudentUser, dishes: DishesRepo):
    return DishTomorrowResponse(dishes=await dishes.get_menu_for_day(student.institution_id, tomorrow_local()))


# ---- поставщик ----
@router.get("/dishes", response_model=DishListResponse, summary="Блюда заведения (поставщик)")
async def get_active_dishes(institution_id: int, provider: Provider, dishes: DishesRepo):
    active = await dishes.get_active(institution_id)
    if not active:
        raise NotFoundError("Dishes not found")
    return DishListResponse(dishes=active)


@router.get("/date_dishes", response_model=DishScheduleListResponse, summary="План на день (поставщик)")
async def get_plan_for_day(institution_id: int, target_date: date, provider: Provider, dishes: DishesRepo):
    return DishScheduleListResponse(dishes=await dishes.get_plan_for_day(institution_id, target_date))


@router.put(
    "/dishes",
    response_model=OkResponse,
    summary="Задать план на день (поставщик)",
    description="Количество порций на день. Уже сделанные заказы сохраняются; "
    "нельзя поставить количество меньше, чем уже заказано.",
)
async def set_plan_for_day(
    institution_id: int, plan: DishPlan, target_date: date, provider: Provider, dishes: DishesRepo
):
    today = today_local()
    if target_date <= today:
        raise BadRequestError("You can not assign past dates")
    if target_date > today + timedelta(days=MAX_PLANNING_DAYS):
        raise BadRequestError("You can only plan one week ahead")
    await dishes.set_plan_for_day(institution_id, plan, target_date)
    return OkResponse()


# ---- оператор раздачи ----
@router.get("/date_dishes_operator", response_model=DishWithQuantityListResponse, summary="Блюда на день (оператор)")
async def get_planned_dishes_for_operator(target_date: date, operator: Operator, dishes: DishesRepo):
    return DishWithQuantityListResponse(dishes=await dishes.get_planned_for_day(operator.institution_id, target_date))
