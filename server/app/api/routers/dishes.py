from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Query

from app.api.deps import Admin, DishesRepo, Operator, Provider, StudentUser
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.schemas.common import OkResponse
from app.schemas.dishes import (
    BuffetCreate,
    BuffetUpdate,
    CreateDishesResponse,
    CycleAnchor,
    DeleteDishesResponse,
    DishCreateList,
    DishListResponse,
    DishPlan,
    DishResponse,
    DishScheduleListResponse,
    DishTomorrowResponse,
    DishUpdate,
    DishWithQuantityListResponse,
    MealSetInput,
    MealSetListResponse,
)
from app.services.menu_calendar import cycle_slot, next_pickup_day

router = APIRouter(prefix="/dishes", tags=["Блюда"])

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


@router.put("/cycle-anchor", response_model=OkResponse)
async def save_anchor(data: CycleAnchor, admin: Admin, dishes: DishesRepo):
    await dishes.set_anchor(admin.institution_id, data.cycle_start_monday)
    return OkResponse()


@router.get("/meal-sets", response_model=MealSetListResponse)
async def list_meal_sets(admin: Admin, dishes: DishesRepo):
    return MealSetListResponse(
        cycle_start_monday=await dishes.anchor(admin.institution_id), sets=await dishes.meal_sets(admin.institution_id)
    )


@router.post("/meal-sets", response_model=OkResponse)
async def create_meal_set(data: MealSetInput, admin: Admin, dishes: DishesRepo):
    await dishes.save_meal_set(admin.institution_id, data)
    return OkResponse()


@router.put("/meal-sets/{meal_id}", response_model=OkResponse)
async def update_meal_set(meal_id: int, data: MealSetInput, admin: Admin, dishes: DishesRepo):
    await dishes.save_meal_set(admin.institution_id, data, meal_id)
    return OkResponse()


@router.delete("/meal-sets/{meal_id}", response_model=OkResponse)
async def delete_meal_set(meal_id: int, admin: Admin, dishes: DishesRepo):
    await dishes.delete_meal_set(admin.institution_id, meal_id)
    return OkResponse()


def buffet_data(offering):
    dish = offering.dish
    return {
        "id": offering.id,
        "dish_id": dish.id,
        "institution_id": dish.institution_id,
        "quantity": offering.quantity,
        "is_visible": offering.is_visible,
        "dish_name": dish.dish_name,
        "category": dish.category,
        "fixed_price": dish.fixed_price,
        "img_url": dish.img_url,
        "serving_weight_g": dish.serving_weight_g,
        "energy_kcal": dish.energy_kcal,
        "protein_g": dish.protein_g,
        "fat_g": dish.fat_g,
        "carbohydrates_g": dish.carbohydrates_g,
    }


@router.get("/buffet")
async def list_buffet(operator: Operator, dishes: DishesRepo):
    return {"offerings": [buffet_data(o) for o in await dishes.buffet(operator.institution_id)]}


@router.get("/buffet/catalog")
async def buffet_catalog(operator: Operator, dishes: DishesRepo):
    active = await dishes.get_active(operator.institution_id)
    return {"dishes": [{"id": dish.id, "dish_name": dish.dish_name} for dish in active]}


@router.post("/buffet")
async def create_buffet(data: BuffetCreate, operator: Operator, dishes: DishesRepo):
    return {"offering": buffet_data(await dishes.create_buffet(operator.institution_id, data.dish_id, data.quantity))}


@router.patch("/buffet/{offering_id}")
async def update_buffet(offering_id: int, data: BuffetUpdate, operator: Operator, dishes: DishesRepo):
    return {
        "offering": buffet_data(
            await dishes.update_buffet(operator.institution_id, offering_id, data.delta, data.is_visible)
        )
    }


def menu_now():
    return datetime.now(UTC)


# ---- студент ----
@router.get("/dishes_tomorrow", response_model=DishTomorrowResponse, summary="Меню на следующий день выдачи")
async def get_menu_for_tomorrow(student: StudentUser, dishes: DishesRepo):
    pickup = next_pickup_day(menu_now(), ZoneInfo(get_settings().timezone))
    anchor = await dishes.anchor(student.institution_id)
    try:
        slot = cycle_slot(anchor, pickup)
    except ValueError:
        sets = []
    else:
        sets = await dishes.meal_sets(student.institution_id, slot)
    offerings = await dishes.buffet(student.institution_id, visible_only=True)
    return DishTomorrowResponse(pickup_date=pickup, dishes=[buffet_data(o) for o in offerings], sets=sets)


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
    summary="Планирование поставщиком отключено",
)
async def set_plan_for_day(
    institution_id: int, plan: DishPlan, target_date: date, provider: Provider, dishes: DishesRepo
):
    raise ForbiddenError("Daily menu planning is no longer available")


# ---- оператор раздачи ----
@router.get("/date_dishes_operator", response_model=DishWithQuantityListResponse, summary="Блюда на день (оператор)")
async def get_planned_dishes_for_operator(target_date: date, operator: Operator, dishes: DishesRepo):
    return DishWithQuantityListResponse(dishes=await dishes.get_planned_for_day(operator.institution_id, target_date))
