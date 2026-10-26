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
    await _ensure_dish_available_to(user, data.dish_id, dishes)
    await baskets.add_dish(student.id, data.dish_id, data.cart_quantity)
    return OkResponse()


@router.delete("/dish", response_model=OkResponse, summary="Убрать блюдо из корзины")
async def remove_dish(
    dish_id: int, user: StudentUser, student: CurrentStudent, baskets: BasketRepo, dishes: DishesRepo
):
    await _ensure_dish_available_to(user, dish_id, dishes)
    await baskets.remove_dish(student.id, dish_id)
    return OkResponse()


@router.post("/quantity", response_model=OkResponse, summary="Изменить количество блюда (0 - удалить)")
async def change_quantity(
    data: BasketItemChange, user: StudentUser, student: CurrentStudent, baskets: BasketRepo, dishes: DishesRepo
):
    if data.cart_quantity > get_settings().max_cart_items:
        raise BadRequestError("Too many dishes")
    await _ensure_dish_available_to(user, data.dish_id, dishes)
    await baskets.set_quantity(student.id, data.dish_id, data.cart_quantity)
    return OkResponse()
