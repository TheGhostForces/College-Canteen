from datetime import date, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from database.repository import DishesRepository
from schemas import DishRequest, UniversalDish, UniversalDishes, Universal, \
    UniversalListDish, DishUpdate, DishCreateList, UniversalWithResult, DishesDateUniversal, DeleteResponse
from security.auth import require_role

router = APIRouter(
    prefix="/dishes",
    tags=["Эндпоинты для блюд"],
)

@router.get("/dish", tags=["Админ"], response_model=UniversalDish)
async def get_dish_by_name(
        name: str,
        admin = Depends(require_role("admin"))
):
    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Dish name cannot be empty")

    dish = await DishesRepository.get_dish(None, admin.institution_id, cleaned_name)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    return {"Ok": True, "dish": dish}

@router.post("/dish", response_model=UniversalWithResult, tags=["Админ"])
async def create_dish(
        dish: DishCreateList,
        admin = Depends(require_role("admin"))
):
    result = await DishesRepository.create_many_dishes(admin.institution_id, dish)
    return {"Ok": True, "Result": result}

@router.delete("/dish", tags=["Админ"], response_model=DeleteResponse)
async def delete_dish(
        dish_ids: Optional[List[int]] = Query(None),
        dish_names: Optional[List[str]] = Query(None),
        admin = Depends(require_role("admin"))
):
    if not dish_ids and not dish_names:
        raise HTTPException(status_code=400, detail="Dish ids or names cannot be empty")
    result = await DishesRepository.delete_dishes(
        admin.institution_id,
        dish_ids,
        dish_names
    )

    if result is None:
        raise HTTPException(
            status_code=500,
            detail="Internal server error while deleting dishes"
        )

    deleted_count, not_found_ids, not_found_names = result

    response_data = {
        "deleted_count": deleted_count,
        "not_found": {}
    }

    if not_found_ids:
        response_data["not_found"]["dish_ids"] = not_found_ids

    if not_found_names:
        response_data["not_found"]["dish_names"] = not_found_names

    if deleted_count == 0 and (not_found_ids or not_found_names):
        raise HTTPException(
            status_code=404,
            detail=response_data
        )

    if deleted_count == 0:
        raise HTTPException(
            status_code=404,
            detail="No dishes found matching the criteria"
        )

    return {
        "Ok": True,
        "data": response_data,
        "message": f"Successfully deleted {deleted_count} dish(es)"
    }

@router.patch("/dish", response_model=Universal, tags=["Админ"])
async def update_dish(
        data: DishUpdate,
        dish_id: int = None,
        dish_name: str = None,
        institution_id: int = None,
        admin = Depends(require_role("admin"))
):
    if dish_id is None and dish_name is None:
        raise HTTPException(status_code=400, detail="Cannot be updated without parameters")
    if dish_name and institution_id is None:
        raise HTTPException(status_code=400, detail="Cannot be updated without institution_id")
    dish = await DishesRepository.get_dish(dish_id, institution_id, dish_name)
    if dish is None:
        raise HTTPException(status_code=404, detail="Dish not found")
    dish = await DishesRepository.update_dish(dish.id, data)
    if dish is None:
        raise HTTPException(status_code=400, detail="Dishes cannot be updated")
    return {"Ok": True}

@router.get("/dishes_tomorrow", tags=["Студент"])
async def get_dishes_tomorrow(
        user = Depends(require_role("student"))
):
    date_tomorrow = date.today() + timedelta(days=1)
    dishes = await DishesRepository.get_dishes_on_next_day(
        institution_id=user.institution_id,
        next_day=date_tomorrow
    )
    return {"Ok": True, "dishes": dishes}

@router.get("/date_dishes", tags=["Поставщик"], response_model=DishesDateUniversal)
async def get_all_dishes_by_date(
        institution_id: int,
        target_date: date,
        provider = Depends(require_role("provider"))
):
    dishes = await DishesRepository.get_all_dishes_with_fixed_by_date(institution_id, target_date)
    return {"Ok": True, "dishes": dishes}

@router.get("/dishes", response_model=UniversalListDish, tags=["Поставщик"])
async def get_all_dishes(
        institution_id: int,
        operator = Depends(require_role("provider"))
):
    dishes = await DishesRepository.get_dishes(institution_id=institution_id)
    if not dishes:
        raise HTTPException(status_code=404, detail="Dishes not found")
    return {"Ok": True, "dishes": dishes}

@router.put(
    "/dishes", response_model=Universal,
    tags=["Поставщик"],
    description="Если придет блюдо с количеством равным 0, то оно не зачислиться в расписание"
)
async def set_dishes_on_day(
        institution_id: int,
        dishes: DishRequest,
        target_date: date,
        operator = Depends(require_role("provider"))
):
    current_day = date.today()
    if target_date <= current_day:
        raise HTTPException(status_code=400, detail="You can not assign past dates")
    if target_date > current_day + timedelta(days=7):
        raise HTTPException(status_code=400, detail="You can only bet for a week.")

    # filtered_items = [item for item in dishes.items if item.cart_quantity > 0]
    # filtered_dishes = DishRequest(items=filtered_items)

    await DishesRepository.set_dishes_on_day(institution_id, dishes, target_date)
    return {"Ok": True}

@router.get("/date_dishes_operator", tags=["Оператор раздачи"], response_model=UniversalDishes)
async def get_dishes_by_date(
        target_date: date,
        operator = Depends(require_role("operator"))
):
    dishes = await DishesRepository.get_fixed_dishes_by_date(operator.institution_id, target_date)
    return {"Ok": True, "dishes": dishes}
