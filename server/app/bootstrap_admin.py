"""Первый администратор: python -m app.bootstrap_admin --email admin@example.ru --name 'Колледж'.

Запускается на сервере после миграций с обычными переменными подключения к БД.
Без аргументов запрашивает email и название учреждения интерактивно.
Существующее учреждение с точным названием используется повторно, иначе создаётся.
Для выбора существующего учреждения по ID используйте --institution-id вместо названия.
Существующий email (любой регистр и роль) всегда отклоняется без изменений.
"""

import argparse
import asyncio

from pydantic import BaseModel, EmailStr, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EducationInstitutionOrm, UsersOrm
from app.db.session import SessionFactory, engine


class BootstrapInput(BaseModel):
    email: EmailStr
    name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("email", "name", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


async def bootstrap_admin(
    session: AsyncSession, email: str, name: str | None = None, institution_id: int | None = None
) -> tuple[int, int]:
    """Одна транзакция: учреждение и новый admin. Не изменяет существующих пользователей."""
    if institution_id is None and name is None:
        raise ValueError("Название учреждения обязательно, если не указан --institution-id")
    data = BootstrapInput(email=email, name=name)
    try:
        async with session.begin():
            existing = await session.scalar(select(UsersOrm.id).where(func.lower(UsersOrm.email) == data.email))
            if existing is not None:
                raise ValueError("Email уже существует. Роль и учреждение существующего пользователя не изменены.")
            if institution_id is not None:
                institution = await session.get(EducationInstitutionOrm, institution_id)
                if institution is None:
                    raise ValueError("Учреждение с указанным ID не найдено.")
                if name is not None and name.strip() != institution.name:
                    raise ValueError("Название не совпадает с учреждением указанного ID.")
            else:
                institutions = list(
                    await session.scalars(
                        select(EducationInstitutionOrm).where(EducationInstitutionOrm.name == data.name)
                    )
                )
                if len(institutions) > 1:
                    raise ValueError("Несколько учреждений с таким названием. Укажите --institution-id.")
                if institutions:
                    institution = institutions[0]
                else:
                    institution = EducationInstitutionOrm(name=data.name)
                    session.add(institution)
                    await session.flush()
            user = UsersOrm(email=data.email, role="admin", institution_id=institution.id)
            session.add(user)
            await session.flush()
            result = user.id, institution.id
        return result
    except IntegrityError:
        raise ValueError("Не удалось создать администратора: конфликт данных. Изменения отменены.") from None


async def _run(email: str, name: str | None, institution_id: int | None) -> tuple[int, int]:
    try:
        async with SessionFactory() as session:
            return await bootstrap_admin(session, email, name, institution_id)
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать администратора учреждения без демоданных и токенов")
    parser.add_argument("--email", help="Email нового администратора")
    parser.add_argument("--name", "--institution-name", dest="name", help="Точное название учреждения")
    parser.add_argument("--institution-id", type=int, help="ID существующего учреждения (вместо названия)")
    args = parser.parse_args()
    try:
        email = args.email if args.email is not None else input("Email нового администратора: ")
        name = args.name
        if args.institution_id is None and name is None:
            name = input("Название учреждения: ")
        user_id, institution_id = asyncio.run(_run(email, name, args.institution_id))
    except (ValidationError, ValueError) as exc:
        parser.exit(1, f"Ошибка: {exc}\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "\nСоздание отменено.\n")
    print(f"Администратор создан: id={user_id}, учреждение id={institution_id}. Вход — через обычный email-код.")


if __name__ == "__main__":
    main()
