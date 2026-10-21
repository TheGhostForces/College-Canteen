from datetime import datetime, timedelta, date
from fastapi import APIRouter, Depends, HTTPException
from database.repository import OrdersRepository, UsersRepository
from schemas import Universal, OrderSchema, OrdersSchema, OrdersSchemaName
from security.auth import require_role, require_student_role

router = APIRouter(
    prefix="/orders",
    tags=["Эндпоинты для заказов"],
)

@router.post("/order", tags=["Студент"], response_model=OrderSchema)
async def create_order(
        student = Depends(require_student_role())
):
    order = await OrdersRepository.create_order(student.id)
    return {"Ok": True, "Order": order}

@router.delete("/order", tags=["Студент"], response_model=Universal)
async def undo_order(
        student = Depends(require_student_role())
):
    if datetime.today().hour >= 16:
        raise HTTPException(status_code=400, detail="Not enough time")
    try:
        await OrdersRepository.undo_order(student.id)
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    return {"Ok": True}

@router.get("/order", tags=["Студент"], response_model=OrdersSchemaName)
async def get_dishes_in_order(
        student = Depends(require_student_role())
):
    orders = await OrdersRepository.get_dishes(student_id=student.id)
    return {"Ok": True, "Name": student.full_name, "Student_ID": student.id, "Orders": orders}

@router.get("/student_order", response_model=OrdersSchemaName, tags=["Оператор раздачи"],
            description="Внимание, в самом конце JSON есть поле Name с именем студента")
async def get_dishes_in_order_by_student_id(
        student_id: int,
        operator = Depends(require_role("operator"))
):
    student = await UsersRepository.get_student(student_id=student_id)
    if student is None:
        raise HTTPException(status_code=404, detail="Student not found")
    orders = await OrdersRepository.get_dishes(student_id=student_id)
    return {"Ok": True, "Name": student.full_name, "Student_ID": student.id, "Orders": orders}

@router.patch("/order", tags=["Оператор раздачи"], response_model=Universal)
async def complete_order_by_student_id(
        student_id: int,
        operator = Depends(require_role("operator"))
):
    await OrdersRepository.complete_order(student_id=student_id)
    return {"Ok": True}

@router.get("/total_quantity", tags=["Поставщик"])
async def get_all_ordered_dishes(
        institution_id: int,
        provider = Depends(require_role("provider"))
):
    dishes = await OrdersRepository.get_all_ordered_dishes(institution_id=institution_id, day=datetime.now().date()+timedelta(days=1))
    return {"Ok": True, "dishes": dishes}

@router.get("/orders", tags=["Поставщик"], response_model=OrdersSchema)
async def get_all_orders_with_numbers(
        institution_id: int,
        provider = Depends(require_role("provider"))
):
    orders = await OrdersRepository.get_orders_with_dishes(institution_id)
    return {"Ok": True, "Orders": orders}

@router.get("/orders_date", tags=["Оператор раздачи"], response_model=OrdersSchema)
async def get_orders_with_numbers_by_date(
        target_date: date,
        operator = Depends(require_role("operator"))
):
    orders = await OrdersRepository.get_orders_with_dishes(operator.institution_id, target_date - timedelta(days=1))
    return {"Ok": True, "Orders": orders}