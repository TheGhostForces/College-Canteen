import re
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.db.enums import DishCategory
from app.schemas.common import OkResponse, OrmModel

_IMG_URL_PATTERN = re.compile(r"^[\w\-./]+$")


def _check_img_url(value: str | None) -> str | None:
    """img_url - относительный путь к файлу в /img: без схемы, без начального "/" и без ".."."""
    if value is None:
        return value
    if not _IMG_URL_PATTERN.match(value) or value.startswith("/") or ".." in value:
        raise ValueError("img_url must be a relative file path")
    return value


class DishCreate(BaseModel):
    dish_name: str = Field(min_length=1, max_length=100)
    category: DishCategory
    fixed_price: int = Field(gt=0, le=100_000)
    img_url: str | None = None

    _validate_img_url = field_validator("img_url")(_check_img_url)


class DishUpdate(BaseModel):
    dish_name: str | None = Field(default=None, min_length=1, max_length=100)
    category: DishCategory | None = None
    fixed_price: int | None = Field(default=None, gt=0, le=100_000)
    img_url: str | None = None

    _validate_img_url = field_validator("img_url")(_check_img_url)


class DishCreateList(BaseModel):
    items: list[DishCreate]


class DishPlanItem(BaseModel):
    """Блюдо и количество порций (в плане на день: сколько приготовить)."""

    dish_id: int
    cart_quantity: int = Field(ge=0, le=100_000)


class DishPlan(BaseModel):
    items: list[DishPlanItem]


# ---- ответы ----
class DishOut(OrmModel):
    id: int
    dish_name: str
    category: str
    fixed_price: int
    img_url: str | None = None


class DishWithQuantityOut(DishOut):
    dish_id: int
    quantity: int


class DishScheduleOut(BaseModel):
    dish_id: int
    dish_name: str
    category: str
    fixed_price: int
    img_url: str | None = None
    total_quantity: int
    quantity: int


class DishResponse(OkResponse):
    dish: DishOut


class DishListResponse(OkResponse):
    dishes: list[DishOut]


class DishWithQuantityListResponse(OkResponse):
    dishes: list[DishWithQuantityOut]


class DishScheduleListResponse(OkResponse):
    dishes: list[DishScheduleOut]


class CreateDishesResult(BaseModel):
    created_dish_ids: list[int]
    created_count: int
    duplicate_dishes: list[str] = []
    duplicate_count: int = 0


class CreateDishesResponse(OkResponse):
    Result: CreateDishesResult


class DeleteDishesData(BaseModel):
    deleted_count: int
    not_found: dict[str, Any] = {}


class DeleteDishesResponse(OkResponse):
    data: DeleteDishesData
    message: str


class DishTomorrowOut(BaseModel):
    id: int | None  # id записи расписания; None, если блюдо на завтра не запланировано
    dish_id: int
    institution_id: int
    dish_name: str
    category: str
    quantity: int
    fixed_price: int
    img_url: str | None = None


class DishTomorrowResponse(OkResponse):
    dishes: list[DishTomorrowOut]
