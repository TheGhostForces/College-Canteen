from fastapi import APIRouter

from app.api.deps import Admin, UsersRepo
from app.core.exceptions import BadRequestError
from app.db.enums import UserRole
from app.schemas.users import StudentCreate, UserCreate

router = APIRouter(prefix="/admin", tags=["Администрирование"])


@router.post("/user", summary="Создать пользователя (для студента - вместе с профилем)")
async def create_user(user: UserCreate, admin: Admin, users: UsersRepo, student: StudentCreate | None = None):
    if user.role == UserRole.STUDENT and student is None:
        raise BadRequestError("User with role student must have information about a student")
    user_id = await users.create(user, student)
    return {"Ok": True, "user_id": user_id}
