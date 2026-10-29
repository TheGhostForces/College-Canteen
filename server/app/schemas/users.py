from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.db.enums import UserRole
from app.schemas.common import OrmModel
from app.schemas.institutions import InstitutionOut


class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole
    # Совместимость со старым клиентом: значение никогда не определяет учреждение.
    institution_id: int | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("role")
    @classmethod
    def disallow_admin(cls, value: UserRole) -> UserRole:
        if value == UserRole.ADMIN:
            raise ValueError("Администратор создаётся только серверной командой bootstrap_admin")
        return value


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    group_name: str = Field(min_length=1, max_length=50)
    date_start: date
    date_end: date

    @field_validator("full_name", "group_name", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def check_dates(self):
        if self.date_end < self.date_start:
            raise ValueError("date_end must not be earlier than date_start")
        return self


class StudentOut(OrmModel):
    id: int
    full_name: str
    group_name: str
    date_start: date
    date_end: date
    rating: int


class UserOut(OrmModel):
    id: int
    email: str
    role: UserRole
    institution_id: int
    student: StudentOut | None = None


class AdminMe(BaseModel):
    id: int
    email: str
    role: UserRole
    institution: InstitutionOut


class UserListResponse(BaseModel):
    users: list[UserOut]
    total: int
    limit: int
    offset: int
