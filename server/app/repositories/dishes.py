from datetime import date

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.db.models import (
    BuffetOfferingOrm,
    DishesOrm,
    EducationInstitutionOrm,
    MealSetComponentOrm,
    MealSetOrm,
    ScheduleDishesOrm,
)
from app.schemas.dishes import DishCreateList, DishPlan, DishUpdate


class DishesRepository:
    """Блюда заведения и их расписание по дням."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def buffet(self, institution_id: int, visible_only: bool = False) -> list[BuffetOfferingOrm]:
        query = (
            select(BuffetOfferingOrm)
            .join(BuffetOfferingOrm.dish)
            .where(DishesOrm.institution_id == institution_id)
            .order_by(BuffetOfferingOrm.id)
        )
        if visible_only:
            query = query.where(
                BuffetOfferingOrm.is_visible.is_(True), BuffetOfferingOrm.quantity > 0, DishesOrm.is_active.is_(True)
            )
        return list((await self.session.execute(query)).scalars())

    async def create_buffet(self, institution_id: int, dish_id: int, quantity: int) -> BuffetOfferingOrm:
        dish = await self.get_by_id(dish_id)
        if dish is None or dish.institution_id != institution_id or not dish.is_active:
            raise NotFoundError("Dish not found")
        offering = BuffetOfferingOrm(dish_id=dish_id, quantity=quantity, dish=dish)
        self.session.add(offering)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Offering already exists") from None
        return offering

    async def update_buffet(self, institution_id: int, offering_id: int, delta: int | None, visible: bool | None):
        query = (
            select(BuffetOfferingOrm)
            .join(BuffetOfferingOrm.dish)
            .where(BuffetOfferingOrm.id == offering_id, DishesOrm.institution_id == institution_id)
            .with_for_update(of=BuffetOfferingOrm)
            .execution_options(populate_existing=True)
        )
        offering = (await self.session.execute(query)).scalar_one_or_none()
        if offering is None:
            raise NotFoundError("Offering not found")
        if delta is not None:
            if offering.quantity + delta < 0:
                raise BadRequestError("Stock cannot be negative")
            offering.quantity += delta
        if visible is not None:
            offering.is_visible = visible
        await self.session.commit()
        return offering

    # ---- справочник блюд ----
    async def get_by_id(self, dish_id: int) -> DishesOrm | None:
        return await self.session.get(DishesOrm, dish_id)

    async def get_by_name(self, institution_id: int, dish_name: str) -> DishesOrm | None:
        query = select(DishesOrm).where(DishesOrm.institution_id == institution_id, DishesOrm.dish_name == dish_name)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def get_active(self, institution_id: int) -> list[DishesOrm]:
        query = select(DishesOrm).where(DishesOrm.institution_id == institution_id, DishesOrm.is_active.is_(True))
        return list((await self.session.execute(query)).scalars().all())

    async def create_many(self, institution_id: int, data: DishCreateList) -> dict:
        names = [item.dish_name.strip() for item in data.items if item.dish_name.strip()]
        if not names:
            raise BadRequestError("No dish names provided")

        existing = await self.session.execute(
            select(DishesOrm).where(DishesOrm.dish_name.in_(names), DishesOrm.institution_id == institution_id)
        )
        existing_by_name = {dish.dish_name: dish for dish in existing.scalars()}

        to_insert: list[DishesOrm] = []
        reactivated: list[DishesOrm] = []
        duplicates: list[str] = []
        seen: set[str] = set()

        for item in data.items:
            name = item.dish_name.strip()
            if not name:
                continue
            if name in seen:
                duplicates.append(name)
                continue
            seen.add(name)

            old = existing_by_name.get(name)
            if old is None:
                to_insert.append(
                    DishesOrm(
                        dish_name=name,
                        category=item.category,
                        fixed_price=item.fixed_price,
                        serving_weight_g=item.serving_weight_g,
                        energy_kcal=item.energy_kcal,
                        protein_g=item.protein_g,
                        fat_g=item.fat_g,
                        carbohydrates_g=item.carbohydrates_g,
                        img_url=item.img_url,
                        institution_id=institution_id,
                    )
                )
            elif not old.is_active:
                # "удалённое" блюдо с тем же именем возвращаем в меню, а не блокируем создание
                old.is_active = True
                old.category = item.category
                old.fixed_price = item.fixed_price
                for field in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g"):
                    setattr(old, field, getattr(item, field))
                if item.img_url is not None:
                    old.img_url = item.img_url
                reactivated.append(old)
            else:
                duplicates.append(name)

        if not to_insert and not reactivated:
            if duplicates:
                raise BadRequestError(f"All dishes already exist: {', '.join(duplicates)}")
            raise BadRequestError("No valid dishes to add")

        self.session.add_all(to_insert)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Some dishes already exist") from None

        created_ids = [dish.id for dish in to_insert + reactivated]
        result = {"created_dish_ids": created_ids, "created_count": len(created_ids)}
        if duplicates:
            result["duplicate_dishes"] = duplicates
            result["duplicate_count"] = len(duplicates)
        return result

    async def update(self, dish_id: int, data: DishUpdate) -> DishesOrm:
        values = data.model_dump(exclude_none=True)
        if not values:
            raise BadRequestError("Nothing to update")
        try:
            await self.session.execute(update(DishesOrm).where(DishesOrm.id == dish_id).values(**values))
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("A dish with this name already exists") from None
        dish = await self.session.get(DishesOrm, dish_id, populate_existing=True)
        return dish

    async def deactivate(
        self, institution_id: int, dish_ids: list[int] | None, dish_names: list[str] | None
    ) -> tuple[int, list[int], list[str]]:
        """Мягкое удаление. Возвращает (сколько скрыто, не найденные id, не найденные имена)."""
        dish_ids = dish_ids or []
        dish_names = dish_names or []

        found = await self.session.execute(
            select(DishesOrm.id, DishesOrm.dish_name).where(
                DishesOrm.institution_id == institution_id,
                (DishesOrm.id.in_(dish_ids)) | (DishesOrm.dish_name.in_(dish_names)),
            )
        )
        rows = found.all()
        found_ids = {row.id for row in rows}
        found_names = {row.dish_name for row in rows}
        not_found_ids = [dish_id for dish_id in dish_ids if dish_id not in found_ids]
        not_found_names = [name for name in dish_names if name not in found_names]

        if not found_ids:
            return 0, not_found_ids, not_found_names

        result = await self.session.execute(
            update(DishesOrm).where(DishesOrm.id.in_(found_ids), DishesOrm.is_active.is_(True)).values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount, not_found_ids, not_found_names

    async def anchor(self, institution_id):
        institution = await self.session.get(EducationInstitutionOrm, institution_id)
        return institution.cycle_start_monday

    async def set_anchor(self, institution_id, anchor):
        institution = await self.session.get(EducationInstitutionOrm, institution_id)
        institution.cycle_start_monday = anchor
        await self.session.commit()

    async def meal_sets(self, institution_id, slot=None):
        query = select(MealSetOrm).where(MealSetOrm.institution_id == institution_id).order_by(MealSetOrm.id)
        if slot is not None:
            query = query.where(MealSetOrm.cycle_week == slot[0], MealSetOrm.weekday == slot[1])
        rows = (await self.session.execute(query)).scalars().all()
        result = []
        for meal in rows:
            components = [component.dish for component in meal.components]
            if slot is not None and any(not dish.is_active for dish in components):
                continue
            fields = ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")
            result.append(
                dict(
                    id=meal.id,
                    cycle_week=meal.cycle_week,
                    weekday=meal.weekday,
                    meal_type=meal.meal_type,
                    price=meal.price,
                    dish_ids=[d.id for d in components],
                    components=components,
                    **{field: sum(getattr(d, field) for d in components) for field in fields},
                )
            )
        return result

    async def save_meal_set(self, institution_id, data, meal_id=None):
        valid = (
            (
                await self.session.execute(
                    select(DishesOrm.id).where(
                        DishesOrm.institution_id == institution_id,
                        DishesOrm.is_active.is_(True),
                        DishesOrm.id.in_(data.dish_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        if set(valid) != set(data.dish_ids):
            raise BadRequestError("Unknown, inactive or foreign components")
        if meal_id is None:
            meal = MealSetOrm(institution_id=institution_id)
            self.session.add(meal)
        else:
            meal = (
                await self.session.execute(
                    select(MealSetOrm)
                    .where(MealSetOrm.id == meal_id, MealSetOrm.institution_id == institution_id)
                    .with_for_update(of=MealSetOrm)
                )
            ).scalar_one_or_none()
            if meal is None:
                raise NotFoundError("Meal set not found")
        meal.cycle_week, meal.weekday, meal.meal_type, meal.price = (
            data.cycle_week,
            data.weekday,
            data.meal_type,
            data.price,
        )
        try:
            if meal_id is not None:
                meal.components.clear()
                await self.session.flush()
            meal.components = [
                MealSetComponentOrm(dish_id=dish_id, position=i) for i, dish_id in enumerate(data.dish_ids)
            ]
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ConflictError("Meal set slot already exists") from None

    async def delete_meal_set(self, institution_id, meal_id):
        meal = (
            await self.session.execute(
                select(MealSetOrm)
                .where(MealSetOrm.id == meal_id, MealSetOrm.institution_id == institution_id)
                .with_for_update(of=MealSetOrm)
            )
        ).scalar_one_or_none()
        if meal is None:
            raise NotFoundError("Meal set not found")
        await self.session.delete(meal)
        await self.session.commit()

    # ---- расписание ----
    async def get_menu_for_day(self, institution_id: int, day: date) -> list[dict]:
        """Все активные блюда с остатком на день (0, если блюдо не запланировано) - для студента."""
        query = (
            select(DishesOrm, ScheduleDishesOrm)
            .outerjoin(
                ScheduleDishesOrm,
                (DishesOrm.id == ScheduleDishesOrm.dish_id) & (ScheduleDishesOrm.date == day),
            )
            .where(DishesOrm.institution_id == institution_id, DishesOrm.is_active.is_(True))
        )
        return [
            {
                "id": schedule.id if schedule else None,
                "dish_id": dish.id,
                "institution_id": dish.institution_id,
                "dish_name": dish.dish_name,
                "category": dish.category,
                "quantity": schedule.quantity if schedule else 0,
                "fixed_price": dish.fixed_price,
                **{
                    field: getattr(dish, field)
                    for field in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")
                },
                "img_url": dish.img_url,
            }
            for dish, schedule in (await self.session.execute(query)).all()
        ]

    async def get_planned_for_day(self, institution_id: int, day: date) -> list[dict]:
        """Блюда, запланированные на день, с полным количеством - для оператора раздачи."""
        query = (
            select(ScheduleDishesOrm)
            .join(DishesOrm)
            .where(ScheduleDishesOrm.date == day, DishesOrm.institution_id == institution_id)
            .options(joinedload(ScheduleDishesOrm.dish))
        )
        items = (await self.session.execute(query)).scalars().all()
        if not items:
            raise NotFoundError(f"Schedule not found for {day}")
        return [
            {
                "id": item.id,
                "dish_id": item.dish_id,
                "institution_id": item.dish.institution_id,
                "dish_name": item.dish.dish_name,
                "category": item.dish.category,
                "quantity": item.total_quantity,
                "fixed_price": item.dish.fixed_price,
                **{
                    field: getattr(item.dish, field)
                    for field in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")
                },
                "img_url": item.dish.img_url,
            }
            for item in items
        ]

    async def get_plan_for_day(self, institution_id: int, day: date) -> list[dict]:
        """Все активные блюда с планом (всего/осталось) на день - для поставщика."""
        query = (
            select(DishesOrm, ScheduleDishesOrm)
            .outerjoin(
                ScheduleDishesOrm,
                (ScheduleDishesOrm.dish_id == DishesOrm.id) & (ScheduleDishesOrm.date == day),
            )
            .where(DishesOrm.institution_id == institution_id, DishesOrm.is_active.is_(True))
            .order_by(DishesOrm.category, DishesOrm.dish_name)
        )
        rows = (await self.session.execute(query)).all()
        if not rows:
            raise NotFoundError(f"No active dishes found for institution {institution_id}")
        return [
            {
                "dish_id": dish.id,
                "dish_name": dish.dish_name,
                "category": dish.category,
                "quantity": schedule.quantity if schedule else 0,
                "total_quantity": schedule.total_quantity if schedule else 0,
                "fixed_price": dish.fixed_price,
                **{
                    field: getattr(dish, field)
                    for field in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")
                },
                "img_url": dish.img_url,
            }
            for dish, schedule in rows
        ]

    async def set_plan_for_day(self, institution_id: int, plan: DishPlan, day: date) -> None:
        """Устанавливает, сколько порций каждого блюда будет на день.

        Уже сделанные заказы сохраняются: остаток = новое количество - уже заказано.
        """
        dish_ids = [item.dish_id for item in plan.items]
        if len(set(dish_ids)) != len(dish_ids):
            raise BadRequestError("Duplicate dishes in request")

        valid = await self.session.execute(
            select(DishesOrm.id)
            .where(
                DishesOrm.id.in_(dish_ids),
                DishesOrm.institution_id == institution_id,
                DishesOrm.is_active.is_(True),
            )
            .order_by(DishesOrm.id)
            .with_for_update()
        )
        invalid_ids = set(dish_ids) - {dish_id for (dish_id,) in valid}
        if invalid_ids:
            raise BadRequestError(f"Unknown, inactive or foreign dishes: {sorted(invalid_ids)}")

        # блокируем строки, чтобы не гоняться с оформлением заказов
        locked = await self.session.execute(
            select(ScheduleDishesOrm)
            .where(ScheduleDishesOrm.dish_id.in_(dish_ids), ScheduleDishesOrm.date == day)
            .order_by(ScheduleDishesOrm.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        schedule_by_dish = {schedule.dish_id: schedule for schedule in locked.scalars()}

        conflicts = []
        for item in plan.items:
            new_total = item.cart_quantity
            schedule = schedule_by_dish.get(item.dish_id)
            if schedule is None:
                self.session.add(
                    ScheduleDishesOrm(date=day, dish_id=item.dish_id, quantity=new_total, total_quantity=new_total)
                )
                continue
            already_ordered = schedule.total_quantity - schedule.quantity
            if new_total < already_ordered:
                conflicts.append({"dish_id": item.dish_id, "already_ordered": already_ordered})
                continue
            schedule.total_quantity = new_total
            schedule.quantity = new_total - already_ordered

        if conflicts:
            raise ConflictError(f"Quantity is lower than already ordered: {conflicts}")
        await self.session.commit()
