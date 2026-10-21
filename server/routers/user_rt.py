from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from database.repository import AdminRepository
from schemas import UserSchema, StudentSchema
from security.auth import require_role

router = APIRouter(
    prefix="/admin",
    tags=["Эндпоинты для добавления, изменения ифнормации о студентах, или изменение их ролей"],
)

@router.post("/user", tags=["Админ"])
async def create_user(
        user: UserSchema,
        student: Optional[StudentSchema] = None,
        admin = Depends(require_role("admin"))
):
    if student is None and user.role.value == "student":
        raise HTTPException(status_code=400, detail="User with role student cannot have information about a student")
    await AdminRepository.add_client(user, student)
    return {"Ok": True}