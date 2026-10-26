"""Демоданные для локального запуска: python -m app.seed (после миграций)."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutils import today_local, tomorrow_local
from app.db.models import (
    DishesOrm,
    EducationInstitutionOrm,
    ScheduleDishesOrm,
    ShoppingCartOrm,
    StudentsOrm,
    UsersOrm,
)
from app.db.session import SessionFactory, engine


async def seed() -> None:
    if get_settings().mail_backend != "console":
        raise RuntimeError("Демоданные разрешены только локально: MAIL_BACKEND=console")

    async with SessionFactory() as session, session.begin():
        institution = await session.scalar(
            select(EducationInstitutionOrm).where(EducationInstitutionOrm.name == "Демонстрационный колледж")
        )
        if institution is None:
            institution = EducationInstitutionOrm(name="Демонстрационный колледж")
            session.add(institution)
            await session.flush()

        for role in ("student", "provider", "operator", "admin"):
            email = f"{role}@example.com"
            user = await session.scalar(select(UsersOrm).where(UsersOrm.email == email))
            if user is None:
                user = UsersOrm(email=email, role=role, institution_id=institution.id)
                session.add(user)
                await session.flush()
            elif user.role != role or user.institution_id != institution.id:
                raise RuntimeError(f"Демоадрес {email} уже занят другим пользователем; данные не изменены")

            if role == "student":
                student = await session.scalar(select(StudentsOrm).where(StudentsOrm.user_id == user.id))
                if student is None:
                    student = StudentsOrm(
                        user_id=user.id,
                        full_name="Демонстрационный студент",
                        group_name="ДЕМО-1",
                        date_start=today_local() - timedelta(days=365),
                        date_end=today_local() + timedelta(days=365 * 4),
                    )
                    session.add(student)
                    await session.flush()
                cart = await session.scalar(select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student.id))
                if cart is None:
                    session.add(ShoppingCartOrm(student_id=student.id))

        for name, category, price in (
            ("Борщ", "Первое", 120),
            ("Курица с рисом", "Второе", 200),
            ("Чай", "Напитки", 30),
            ("Булочка", "Десерт", 50),
        ):
            dish = await session.scalar(
                select(DishesOrm).where(DishesOrm.institution_id == institution.id, DishesOrm.dish_name == name)
            )
            if dish is None:
                dish = DishesOrm(dish_name=name, category=category, fixed_price=price, institution_id=institution.id)
                session.add(dish)
                await session.flush()
            schedule = await session.scalar(
                select(ScheduleDishesOrm).where(
                    ScheduleDishesOrm.dish_id == dish.id, ScheduleDishesOrm.date == tomorrow_local()
                )
            )
            if schedule is None and dish.is_active:
                session.add(ScheduleDishesOrm(dish_id=dish.id, date=tomorrow_local(), quantity=50, total_quantity=50))

    print("Демоданные готовы. Вход: student/provider/operator/admin@example.com; коды — в логах приложения.")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
