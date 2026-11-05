"""Демоданные для локального запуска: python -m app.seed (после миграций)."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutils import today_local
from app.db.models import (
    BuffetOfferingOrm,
    DishesOrm,
    EducationInstitutionOrm,
    MealSetComponentOrm,
    MealSetOrm,
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
                        study_start_year=today_local().year - 1,
                        study_end_year=today_local().year + 4,
                    )
                    session.add(student)
                    await session.flush()
                cart = await session.scalar(select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student.id))
                if cart is None:
                    session.add(ShoppingCartOrm(student_id=student.id))

        if institution.cycle_start_monday is None:
            today = today_local()
            institution.cycle_start_monday = today - timedelta(days=today.weekday())

        dishes = {}
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
            dishes[name] = dish

        for week in (1, 2):
            for weekday in range(5):
                meal = await session.scalar(
                    select(MealSetOrm).where(
                        MealSetOrm.institution_id == institution.id,
                        MealSetOrm.cycle_week == week,
                        MealSetOrm.weekday == weekday,
                        MealSetOrm.meal_type == "lunch",
                    )
                )
                if meal is None and all(dishes[name].is_active for name in ("Борщ", "Курица с рисом")):
                    meal = MealSetOrm(
                        institution_id=institution.id, cycle_week=week, weekday=weekday, meal_type="lunch", price=300
                    )
                    meal.components = [
                        MealSetComponentOrm(dish_id=dishes[name].id, position=position)
                        for position, name in enumerate(("Борщ", "Курица с рисом"))
                    ]
                    session.add(meal)

        for name in ("Чай", "Булочка"):
            dish = dishes[name]
            offering = await session.scalar(select(BuffetOfferingOrm).where(BuffetOfferingOrm.dish_id == dish.id))
            if offering is None and dish.is_active:
                session.add(BuffetOfferingOrm(dish_id=dish.id, quantity=50, is_visible=True))

    print("Демоданные готовы. Вход: student/provider/operator/admin@example.com; коды — в логах приложения.")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
