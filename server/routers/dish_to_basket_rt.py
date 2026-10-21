from fastapi import APIRouter, Depends, HTTPException
from database.repository import BasketDishesRepository, DishesRepository
from schemas import DishToBasket, Universal, DishListBasket
from security.auth import require_role, require_student_role, get_current_student_from_token

router = APIRouter(
    prefix="/basket",
    tags=["Эндпоинты для блюд в корзине"],
)

@router.get("/dish", response_model=DishListBasket, tags=["Студент"])
async def get_dishes_in_basket(
        student = Depends(require_student_role())
):
    basket = await BasketDishesRepository.get_basket(student_id=student.id)
    if not basket:
        raise HTTPException(status_code=404, detail="Basket not found")
    dishes = await BasketDishesRepository.get_dishes(shoppingcart_id=basket.id)
    return {"Ok": True, "dishes": dishes}

@router.post("/dish", response_model=Universal, tags=["Студент"])
async def add_dish_to_basket(
        data: DishToBasket,
        user = Depends(require_role("student")),
        student = Depends(get_current_student_from_token)
):
    dish = await DishesRepository.get_dish(dish_id=data.dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    if dish.institution_id != user.institution_id:
        raise HTTPException(status_code=400, detail="This dish does not belong to this student")
    if data.cart_quantity > 5:
        raise HTTPException(status_code=400, detail="Too many dishes")
    await BasketDishesRepository.add_dish_to_basket(student.id, data)
    return {"Ok": True}

@router.delete("/dish", response_model=Universal, tags=["Студент"])
async def remove_dish_from_basket(
        dish_id: int,
        user = Depends(require_role("student")),
        student = Depends(get_current_student_from_token)
):
    dish = await DishesRepository.get_dish(dish_id=dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    if dish.institution_id != user.institution_id:
        raise HTTPException(status_code=400, detail="This dish does not belong to this student")

    await BasketDishesRepository.delete_dish_from_basket(student.id, dish_id)
    return {"Ok": True}

@router.post("/quantity", response_model=Universal, tags=["Студент"])
async def update_quantity(
        data: DishToBasket,
        user = Depends(require_role("student")),
        student = Depends(get_current_student_from_token)
):
    dish = await DishesRepository.get_dish(dish_id=data.dish_id)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    if dish.institution_id != user.institution_id:
        raise HTTPException(status_code=400, detail="This dish does not belong to this student")
    if data.cart_quantity > 5:
        raise HTTPException(status_code=400, detail="Too many dishes")
    await BasketDishesRepository.change_quantity(student.id, data)
    return {"Ok": True}