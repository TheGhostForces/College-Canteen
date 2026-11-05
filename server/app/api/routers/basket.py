from fastapi import APIRouter

from app.api.deps import BasketRepo, CurrentStudent, DishesRepo, StudentUser
from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.db.models import UsersOrm
from app.schemas.basket import BasketItemChange, BasketResponse
from app.schemas.common import OkResponse

router = APIRouter(prefix="/basket", tags=["Корзина"])


async def _ensure_dish_available_to(user: UsersOrm, dish_id: int, dishes: DishesRepo) -> None:
    dish = await dishes.get_by_id(dish_id)
    if dish is None or not dish.is_active:
        raise NotFoundError("Dish not found")
    if dish.institution_id != user.institution_id:
        raise BadRequestError("This dish does not belong to this student")


@router.get("/dish", response_model=BasketResponse, summary="Содержимое корзины")
async def get_basket(student: CurrentStudent, baskets: BasketRepo):
    basket = await baskets.get_by_student(student.id)
    if basket is None:
        raise NotFoundError("Basket not found")
    return BasketResponse(dishes=await baskets.get_items(basket.id))


@router.post("/dish", response_model=OkResponse, summary="Добавить блюдо в корзину")
async def add_dish(
    data: BasketItemChange, user: StudentUser, student: CurrentStudent, baskets: BasketRepo, dishes: DishesRepo
):
    if data.cart_quantity < 1:
        raise BadRequestError("Quantity must be positive")
    if data.cart_quantity > get_settings().max_cart_items:
        raise BadRequestError("Too many dishes")
    if data.item_type is not None:
        await baskets.add_typed(student.id, data)
    else:
        await _ensure_dish_available_to(user, data.dish_id, dishes)
        await baskets.add_dish(student.id, data.dish_id, data.cart_quantity)
    return OkResponse()


@router.delete("/dish", response_model=OkResponse, summary="Убрать блюдо из корзины")
async def remove_dish(
    user: StudentUser,
    student: CurrentStudent,
    baskets: BasketRepo,
    dishes: DishesRepo,
    dish_id: int | None = None,
    item_type: str | None = None,
    buffet_offering_id: int | None = None,
    meal_set_id: int | None = None,
):
    if item_type in ("buffet", "set"):
        item_id = buffet_offering_id if item_type == "buffet" else meal_set_id
        if item_id is None:
            raise BadRequestError("Item identifier required")
        await baskets.remove_typed(student.id, item_type, item_id)
    elif dish_id is not None and item_type is None:
        await _ensure_dish_available_to(user, dish_id, dishes)
        await baskets.remove_dish(student.id, dish_id)
    else:
        raise BadRequestError("Item identifier required")
    return OkResponse()


@router.post("/quantity", response_model=OkResponse, summary="Изменить количество блюда (0 - удалить)")
async def change_quantity(
    data: BasketItemChange, user: StudentUser, student: CurrentStudent, baskets: BasketRepo, dishes: DishesRepo
):
    if data.cart_quantity > get_settings().max_cart_items:
        raise BadRequestError("Too many dishes")
    if data.item_type is not None:
        await baskets.add_typed(student.id, data, set_quantity=True)
    else:
        await _ensure_dish_available_to(user, data.dish_id, dishes)
        await baskets.set_quantity(student.id, data.dish_id, data.cart_quantity)
    return OkResponse()
