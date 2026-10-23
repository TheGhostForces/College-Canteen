from datetime import date

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.db.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole
    institution_id: int

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class StudentCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    group_name: str = Field(min_length=1, max_length=50)
    date_start: date
    date_end: date

    @model_validator(mode="after")
    def check_dates(self):
        if self.date_end < self.date_start:
            raise ValueError("date_end must not be earlier than date_start")
        return self
