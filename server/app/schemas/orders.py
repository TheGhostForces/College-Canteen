from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import OrderStatus
from app.schemas.common import OkResponse
from app.schemas.dishes import DishOut


class OrderCreated(BaseModel):
    order_number: str
    added_items: int


class OrderCreatedResponse(OkResponse):
    Order: OrderCreated


class OrderItemOut(DishOut):
    order_id: int
    total_price: int
    created_at: datetime
    dish_id: int
    quantity: int


class OrdersResponse(OkResponse):
    Orders: dict[str, list[OrderItemOut]]


class StudentOrdersResponse(OrdersResponse):
    Name: str
    Student_ID: int


class OrderedDishOut(BaseModel):
    id: int
    dish_id: int
    institution_id: int
    dish_name: str
    category: str
    total_quantity: int
    remains_quantity: int
    ordered_quantity: int
    fixed_price: int
    date: date
    img_url: str | None = None


class OrderedDishesResponse(OkResponse):
    dishes: list[OrderedDishOut]


class HistoryDishOut(BaseModel):
    dish_id: int
    quantity: int
    dish_name: str
    fixed_price: int
    total_price: int
    date: date


class HistoryOrderOut(BaseModel):
    order_id: int
    order_number: str
    order_status: OrderStatus
    dishes: list[HistoryDishOut]


class HistoryResponse(OkResponse):
    history: list[HistoryOrderOut]


class PickupTokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pickup_token: str = Field(min_length=1, max_length=2048)


class PickupTokenResponse(BaseModel):
    pickup_token: str
    expires_at: datetime
