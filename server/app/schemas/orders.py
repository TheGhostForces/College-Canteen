from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.enums import OrderStatus
from app.schemas.common import OkResponse
from app.schemas.dishes import DishBasicOut


class OrderCreated(BaseModel):
    order_number: str
    added_items: int


class OrderCreatedResponse(OkResponse):
    Order: OrderCreated


class OrderItemOut(DishBasicOut):
    order_id: int
    total_price: int
    created_at: datetime
    dish_id: int | None = None
    quantity: int
    item_type: str | None = None
    buffet_offering_id: int | None = None
    meal_set_id: int | None = None
    meal_type: str | None = None
    pickup_date: date | None = None
    components: list[dict] = []
    serving_weight_g: float | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbohydrates_g: float | None = None


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


class SupplierSetReportItem(BaseModel):
    meal_set_id: int
    meal_type: str
    quantity: int
    components: list[dict] = Field(default_factory=list)


class SupplierBuffetReportItem(BaseModel):
    buffet_offering_id: int
    dish_name: str
    quantity: int


class SupplierReportResponse(BaseModel):
    sets: list[SupplierSetReportItem]
    buffet: list[SupplierBuffetReportItem]


class HistoryDishOut(BaseModel):
    dish_id: int | None = None
    item_type: str | None = None
    buffet_offering_id: int | None = None
    meal_set_id: int | None = None
    meal_type: str | None = None
    components: list[dict] = []
    category: str | None = None
    img_url: str | None = None
    serving_weight_g: float | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbohydrates_g: float | None = None
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
