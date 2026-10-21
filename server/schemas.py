from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr
from datetime import date, datetime
from database.enums import UserRoles, StatusOrder


class UserSchema(BaseModel):
    login: str
    email: EmailStr
    role: UserRoles
    institution_id: int

class StudentSchema(BaseModel):
    full_name: str
    date_start: date
    date_end: date

class Token(BaseModel):
    access_token: str
    token_type: str

class DishAdd(BaseModel):
    dish_name: str
    category: str
    fixed_price: int
    img_url: Optional[str] = None

class DishUpdate(BaseModel):
    dish_name: Optional[str] = None
    category: Optional[str] = None
    fixed_price: Optional[int] = None
    img_url: Optional[str] = None

class Dish(DishAdd):
    id: int

class Orders(Dish):
    order_id: int
    total_price: int
    created_at: datetime
    dish_id: int
    quantity: int

class Dishes(Dish):
    dish_id: int
    quantity: int

class DishesDate(DishAdd):
    total_quantity: int
    dish_id: int
    quantity: int

class DishesBasket(Dishes):
    total_price: int
    schedule_quantity: int
    date: date
    schedule_dish_id: int

class Institution(BaseModel):
    id: int
    name: str

class Order(BaseModel):
    order_number: str
    added_items: int

class DishHistory(BaseModel):
    dish_id: int
    quantity: int
    dish_name: str
    fixed_price: int
    total_price: int
    date: date

class OrderHistory(BaseModel):
    order_id: int
    order_number: str
    order_status: StatusOrder
    dishes: List[DishHistory]

class DeleteResponseData(BaseModel):
    deleted_count: int
    not_found: Dict[str, Any] = {}

class DishToBasket(BaseModel):
    dish_id: int
    cart_quantity: int

class DishRequest(BaseModel):
    items: List[DishToBasket]

class DishCreateList(BaseModel):
    items: List[DishAdd]

class Universal(BaseModel):
    Ok: bool = True

class InstitutionsUniversal(Universal):
    Institutions: List[Institution]

class OrderSchema(Universal):
    Order: Order

class OrdersSchema(Universal):
    Orders: Dict[str, List[Orders]]

class OrdersSchemaName(OrdersSchema):
    Name: str
    Student_ID: int

class DishListBasket(Universal):
    dishes: List[DishesBasket]

class DishesDateUniversal(Universal):
    dishes: List[DishesDate]

class UniversalOrderHistory(Universal):
    history: List[OrderHistory]

class UniversalStudent(Universal):
    user_id: int
    tmp_code_id: int

class UniversalDish(Universal):
    dish: Dish

class UniversalListDish(Universal):
    dishes: List[Dish]

class UniversalDishes(Universal):
    dishes: List[Dishes]

class Result(BaseModel):
    created_dish_ids: List[int]
    created_count: int
    duplicate_dishes: List[str] = []
    duplicate_count: int = 0

class UniversalWithResult(Universal):
    Result: Result

class DeleteResponse(Universal):
    data: DeleteResponseData
    message: str