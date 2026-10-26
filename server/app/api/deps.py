"""Зависимости FastAPI: сессия БД, репозитории, текущий пользователь и проверка ролей."""

from collections.abc import Callable
from typing import Annotated

import jwt
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.db.enums import UserRole
from app.db.models import StudentsOrm, UsersOrm
from app.db.session import get_session
from app.repositories.baskets import BasketRepository
from app.repositories.dishes import DishesRepository
from app.repositories.institutions import InstitutionsRepository
from app.repositories.login_codes import LoginCodesRepository
from app.repositories.orders import OrdersRepository
from app.repositories.users import UsersRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _repo_dependency(repository_class: type) -> Callable:
    def dependency(session: SessionDep):
        return repository_class(session)

    return dependency


UsersRepo = Annotated[UsersRepository, Depends(_repo_dependency(UsersRepository))]
LoginCodesRepo = Annotated[LoginCodesRepository, Depends(_repo_dependency(LoginCodesRepository))]
InstitutionsRepo = Annotated[InstitutionsRepository, Depends(_repo_dependency(InstitutionsRepository))]
DishesRepo = Annotated[DishesRepository, Depends(_repo_dependency(DishesRepository))]
BasketRepo = Annotated[BasketRepository, Depends(_repo_dependency(BasketRepository))]
OrdersRepo = Annotated[OrdersRepository, Depends(_repo_dependency(OrdersRepository))]


async def get_current_user(request: Request, users: UsersRepo) -> UsersOrm:
    """Пользователь по JWT из HttpOnly-cookie `access_token`."""
    token = request.cookies.get("access_token")
    if not token:
        raise UnauthorizedError("Not authenticated")
    token = token.removeprefix("Bearer ")
    try:
        user_id = decode_access_token(token)
    except (jwt.PyJWTError, ValueError):
        raise UnauthorizedError("Token has expired or is invalid") from None

    user = await users.get_by_id(user_id)
    if user is None:
        raise UnauthorizedError("User not found")
    return user


CurrentUser = Annotated[UsersOrm, Depends(get_current_user)]


def require_role(role: UserRole) -> Callable:
    async def checker(user: CurrentUser) -> UsersOrm:
        if user.role != role.value:
            raise ForbiddenError("Insufficient permissions")
        return user

    return checker


StudentUser = Annotated[UsersOrm, Depends(require_role(UserRole.STUDENT))]
Provider = Annotated[UsersOrm, Depends(require_role(UserRole.PROVIDER))]
Operator = Annotated[UsersOrm, Depends(require_role(UserRole.OPERATOR))]
Admin = Annotated[UsersOrm, Depends(require_role(UserRole.ADMIN))]


async def get_current_student(user: StudentUser, users: UsersRepo) -> StudentsOrm:
    student = await users.get_student_by_user_id(user.id)
    if student is None:
        raise ForbiddenError("Student profile not found")
    return student


CurrentStudent = Annotated[StudentsOrm, Depends(get_current_student)]
