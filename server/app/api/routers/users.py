from fastapi import APIRouter, Query

from app.api.deps import Admin, DishesRepo, UsersRepo
from app.core.exceptions import NotFoundError
from app.schemas.dishes import DishListResponse
from app.schemas.users import AdminMe, StudentCreate, UserCreate, UserListResponse

router = APIRouter(prefix="/admin", tags=["Администрирование"])


@router.get("/me", response_model=AdminMe, summary="Администратор и его учреждение")
async def get_me(admin: Admin, users: UsersRepo):
    institution = await users.get_institution(admin.institution_id)
    if institution is None:
        raise NotFoundError("Institution not found")
    return AdminMe(id=admin.id, email=admin.email, role=admin.role, institution=institution)


@router.get("/users", response_model=UserListResponse, summary="Пользователи своего учреждения")
async def list_users(
    admin: Admin, users: UsersRepo, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0)
):
    items, total = await users.list_for_institution(admin.institution_id, limit, offset)
    return UserListResponse(users=items, total=total, limit=limit, offset=offset)


@router.get("/dishes", response_model=DishListResponse, summary="Активные блюда своего учреждения")
async def list_dishes(admin: Admin, dishes: DishesRepo):
    return DishListResponse(dishes=await dishes.get_active(admin.institution_id))


@router.post("/user", summary="Создать пользователя (для студента — вместе с профилем)")
async def create_user(user: UserCreate, admin: Admin, users: UsersRepo, student: StudentCreate | None = None):
    user_id = await users.create(user, institution_id=admin.institution_id, student=student)
    return {"Ok": True, "user_id": user_id}
