from fastapi import APIRouter, Depends
from database.repository import HistoryRepository
from schemas import UniversalOrderHistory
from security.auth import require_student_role

router = APIRouter(
    prefix="/history",
    tags=["Эндпоинты для истории заказов"],
)

@router.get("/history", response_model=UniversalOrderHistory, tags=["Студент"])
async def get_history(
        month: int = None,
        year: int = None,
        student = Depends(require_student_role())
):
    history = await HistoryRepository.get_history_for_month(student.id, month, year)
    return {"Ok": True, "history": history}