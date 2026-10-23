from datetime import date

from pydantic import BaseModel, Field

from app.schemas.common import OkResponse
from app.schemas.dishes import DishWithQuantityOut


class BasketItemChange(BaseModel):
    dish_id: int
    cart_quantity: int = Field(ge=0, le=100_000)


class BasketItemOut(DishWithQuantityOut):
    total_price: int
    schedule_quantity: int
    date: date
    schedule_dish_id: int


class BasketResponse(OkResponse):
    dishes: list[BasketItemOut]
