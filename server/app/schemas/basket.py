from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import OkResponse


class BasketItemChange(BaseModel):
    dish_id: int | None = None
    item_type: Literal["buffet", "set"] | None = None
    buffet_offering_id: int | None = None
    meal_set_id: int | None = None
    cart_quantity: int = Field(ge=0, le=100_000)

    @model_validator(mode="after")
    def validate_item(self):
        if (
            self.item_type == "buffet"
            and self.buffet_offering_id is not None
            and self.meal_set_id is None
            and self.dish_id is None
        ):
            return self
        if (
            self.item_type == "set"
            and self.meal_set_id is not None
            and self.buffet_offering_id is None
            and self.dish_id is None
        ):
            return self
        raise ValueError("Specify one item kind and its identifier")


class BasketItemOut(BaseModel):
    id: int
    item_type: str | None = None
    buffet_offering_id: int | None = None
    meal_set_id: int | None = None
    meal_type: str | None = None
    dish_id: int | None = None
    dish_name: str
    category: str
    fixed_price: int
    img_url: str | None = None
    serving_weight_g: float | None = None
    energy_kcal: float | None = None
    protein_g: float | None = None
    fat_g: float | None = None
    carbohydrates_g: float | None = None
    quantity: int
    total_price: int
    schedule_quantity: int | None = None
    date: date
    schedule_dish_id: int | None = None
    components: list[dict] = []
    institution_id: int


class BasketResponse(OkResponse):
    dishes: list[BasketItemOut]
