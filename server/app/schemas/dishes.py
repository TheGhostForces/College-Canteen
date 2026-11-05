import re
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import OkResponse, OrmModel

_IMG_URL_PATTERN = re.compile(r"^[\w\-./]+$")


def _check_img_url(value: str | None) -> str | None:
    """img_url - относительный путь к файлу в /img: без схемы, без начального "/" и без ".."."""
    if value is None:
        return value
    if not _IMG_URL_PATTERN.match(value) or value.startswith("/") or ".." in value:
        raise ValueError("img_url must be a relative file path")
    return value


def _strip_category(value):
    return value.strip() if isinstance(value, str) else value


class DishCreate(BaseModel):
    dish_name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    fixed_price: int = Field(gt=0, le=100_000)
    serving_weight_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    energy_kcal: float = Field(default=0, ge=0, allow_inf_nan=False)
    protein_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    fat_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    carbohydrates_g: float = Field(default=0, ge=0, allow_inf_nan=False)
    img_url: str | None = None

    _validate_img_url = field_validator("img_url")(_check_img_url)
    _normalize_category = field_validator("category", mode="before")(_strip_category)


class DishUpdate(BaseModel):
    dish_name: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=100)
    fixed_price: int | None = Field(default=None, gt=0, le=100_000)
    serving_weight_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    energy_kcal: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    protein_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    fat_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    carbohydrates_g: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    img_url: str | None = None

    _validate_img_url = field_validator("img_url")(_check_img_url)
    _normalize_category = field_validator("category", mode="before")(_strip_category)


class DishCreateList(BaseModel):
    items: list[DishCreate]


class DishPlanItem(BaseModel):
    """Блюдо и количество порций (в плане на день: сколько приготовить)."""

    dish_id: int
    cart_quantity: int = Field(ge=0, le=100_000)


class DishPlan(BaseModel):
    items: list[DishPlanItem]


# ---- ответы ----
class DishBasicOut(OrmModel):
    id: int
    dish_name: str
    category: str
    fixed_price: int
    img_url: str | None = None


class DishOut(DishBasicOut):
    serving_weight_g: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float


class DishWithQuantityOut(DishOut):
    dish_id: int
    quantity: int


class DishScheduleOut(BaseModel):
    dish_id: int
    dish_name: str
    category: str
    fixed_price: int
    serving_weight_g: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
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
    serving_weight_g: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float
    img_url: str | None = None


class BuffetCreate(BaseModel):
    dish_id: int
    quantity: int = Field(ge=0, le=100000)


class BuffetUpdate(BaseModel):
    delta: int | None = Field(default=None, ge=-100000, le=100000)
    is_visible: bool | None = None


class CycleAnchor(BaseModel):
    cycle_start_monday: date | None

    @field_validator("cycle_start_monday")
    @classmethod
    def monday_only(cls, value):
        if value is not None and value.weekday() != 0:
            raise ValueError("Cycle anchor must be a Monday")
        return value


class MealSetInput(BaseModel):
    cycle_week: int = Field(ge=1, le=2)
    weekday: int = Field(ge=0, le=4)
    meal_type: Literal["breakfast", "lunch", "afternoon_snack", "dinner"]
    price: int = Field(gt=0, le=100000)
    dish_ids: list[int] = Field(min_length=1, max_length=100)

    @field_validator("dish_ids")
    @classmethod
    def unique_dishes(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Duplicate components")
        return value


class MealSetOut(BaseModel):
    id: int
    cycle_week: int
    weekday: int
    meal_type: str
    price: int
    dish_ids: list[int]
    components: list[DishOut]
    serving_weight_g: float
    energy_kcal: float
    protein_g: float
    fat_g: float
    carbohydrates_g: float


class MealSetListResponse(OkResponse):
    cycle_start_monday: date | None
    sets: list[MealSetOut]


class DishTomorrowResponse(OkResponse):
    pickup_date: date
    dishes: list[DishTomorrowOut]
    sets: list[MealSetOut]
