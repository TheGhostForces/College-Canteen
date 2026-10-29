from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestError, ConflictError
from app.db.enums import UserRole
from app.db.models import EducationInstitutionOrm, StudentsOrm, UsersOrm
from app.schemas.users import StudentCreate, UserCreate


class UsersRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: int) -> UsersOrm | None:
        return await self.session.get(UsersOrm, user_id)

    async def get_by_email(self, email: str) -> UsersOrm | None:
        # email хранится в том регистре, в каком его завели, поэтому сравниваем без учёта регистра
        query = select(UsersOrm).where(func.lower(UsersOrm.email) == email.strip().lower())
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_student_by_user_id(self, user_id: int) -> StudentsOrm | None:
        query = select(StudentsOrm).where(StudentsOrm.user_id == user_id)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_student_by_id(self, student_id: int) -> StudentsOrm | None:
        return await self.session.get(StudentsOrm, student_id)

    async def get_student_institution_id(self, student_id: int) -> int | None:
        query = (
            select(UsersOrm.institution_id)
            .join(StudentsOrm, StudentsOrm.user_id == UsersOrm.id)
            .where(StudentsOrm.id == student_id)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_institution(self, institution_id: int) -> EducationInstitutionOrm | None:
        return await self.session.get(EducationInstitutionOrm, institution_id)

    async def list_for_institution(self, institution_id: int, limit: int, offset: int) -> tuple[list[UsersOrm], int]:
        scope = UsersOrm.institution_id == institution_id
        total = await self.session.scalar(select(func.count()).select_from(UsersOrm).where(scope))
        query = (
            select(UsersOrm)
            .where(scope)
            .options(selectinload(UsersOrm.student))
            .order_by(UsersOrm.id)
            .limit(limit)
            .offset(offset)
        )
        return list((await self.session.scalars(query)).all()), total

    async def create(self, user: UserCreate, institution_id: int, student: StudentCreate | None = None) -> int:
        """Создаёт пользователя только в учреждении, переданном сервером."""
        if user.role not in (UserRole.STUDENT, UserRole.PROVIDER, UserRole.OPERATOR):
            raise BadRequestError("Admin creation is only allowed through bootstrap_admin")
        if user.role != UserRole.STUDENT and student is not None:
            raise BadRequestError("Student data is only allowed for role student")
        email_taken = select(exists().where(func.lower(UsersOrm.email) == user.email.lower()))
        if (await self.session.execute(email_taken)).scalar():
            raise ConflictError(f"User with email '{user.email}' already exists")

        user_orm = UsersOrm(email=user.email, role=user.role.value, institution_id=institution_id)
        if user.role == UserRole.STUDENT:
            if student is None:
                raise BadRequestError("Student data is required for role student")
            user_orm.student = StudentsOrm(
                full_name=student.full_name,
                group_name=student.group_name,
                date_start=student.date_start,
                date_end=student.date_end,
            )

        self.session.add(user_orm)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("User already exists or institution does not exist") from None
        return user_orm.id
