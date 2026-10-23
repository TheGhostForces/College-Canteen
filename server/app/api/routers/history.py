from fastapi import APIRouter, Query

from app.api.deps import CurrentStudent, OrdersRepo
from app.core.timeutils import now_local
from app.schemas.orders import HistoryResponse

router = APIRouter(prefix="/history", tags=["История заказов"])


@router.get("/history", response_model=HistoryResponse, summary="История заказов за месяц (студент)")
async def get_history(
    student: CurrentStudent,
    orders: OrdersRepo,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2020, le=2100),
):
    if month is None or year is None:
        now = now_local()
        month, year = now.month, now.year
    return HistoryResponse(history=await orders.get_history(student.id, year, month))
