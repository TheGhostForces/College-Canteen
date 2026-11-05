from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.models import (
    BuffetOfferingOrm,
    DishesOrm,
    EducationInstitutionOrm,
    MealSetOrm,
    ScheduleDishesOrm,
    ShoppingCartDishesOrm,
    ShoppingCartOrm,
    StudentsOrm,
    TypedCartItemOrm,
    UsersOrm,
)
from app.services.menu_calendar import cycle_slot, next_pickup_day


def menu_now():
    return datetime.now(UTC)


def pickup_day():
    return next_pickup_day(menu_now(), ZoneInfo(get_settings().timezone))


def dish_snapshot(dish):
    return {
        key: getattr(dish, key)
        for key in (
            "dish_name",
            "category",
            "img_url",
            "serving_weight_g",
            "energy_kcal",
            "protein_g",
            "fat_g",
            "carbohydrates_g",
        )
    } | {"dish_id": dish.id}


def set_material(details):
    return {"meal_type": details["meal_type"], "components": details["components"]}


class BasketRepository:
    """Корзина студента. Корзина всегда собирается на завтрашний день."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ---- чтение ----
    async def get_by_student(self, student_id: int) -> ShoppingCartOrm | None:
        query = (
            select(ShoppingCartOrm)
            .where(ShoppingCartOrm.student_id == student_id)
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def create_for_student(self, student_id: int) -> ShoppingCartOrm:
        await self.lock_student(student_id)
        basket = await self.get_by_student(student_id) or await self._create_basket(student_id)
        await self.session.commit()
        return basket

    async def get_items(self, basket_id: int) -> list[dict]:
        query = (
            select(ShoppingCartDishesOrm)
            .options(selectinload(ShoppingCartDishesOrm.schedule_dish).selectinload(ScheduleDishesOrm.dish))
            .where(ShoppingCartDishesOrm.shoppingcart_id == basket_id)
        )
        items = (await self.session.execute(query)).scalars().all()
        legacy = [
            {
                "id": item.id,
                "dish_id": item.schedule_dish.dish_id,
                "schedule_dish_id": item.schedule_dish_id,
                "date": item.schedule_dish.date,
                "quantity": item.cart_quantity,
                "dish_name": item.schedule_dish.dish.dish_name,
                "institution_id": item.schedule_dish.dish.institution_id,
                "category": item.schedule_dish.dish.category,
                "fixed_price": item.schedule_dish.dish.fixed_price,
                "total_price": item.cart_quantity * item.schedule_dish.dish.fixed_price,
                "img_url": item.schedule_dish.dish.img_url,
                "schedule_quantity": item.schedule_dish.quantity,
            }
            for item in items
        ]
        typed = (
            (await self.session.execute(select(TypedCartItemOrm).where(TypedCartItemOrm.cart_id == basket_id)))
            .scalars()
            .all()
        )
        for item in typed:
            details = await self.typed_details(item)
            if details:
                legacy.append(
                    {
                        **details,
                        "id": item.id,
                        "quantity": item.quantity,
                        "total_price": item.quantity * details["fixed_price"],
                        "date": item.pickup_date,
                    }
                )
        return legacy

    async def typed_details(self, item, lock=False):
        if item.buffet_offering_id is not None:
            query = select(BuffetOfferingOrm).where(BuffetOfferingOrm.id == item.buffet_offering_id)
            if lock:
                query = query.with_for_update(of=BuffetOfferingOrm).execution_options(populate_existing=True)
            offering = (await self.session.execute(query)).scalar_one_or_none()
            if offering is None:
                return None
            dish = offering.dish
            return {
                **dish_snapshot(dish),
                "item_type": "buffet",
                "buffet_offering_id": offering.id,
                "institution_id": dish.institution_id,
                "fixed_price": dish.fixed_price,
                "schedule_quantity": offering.quantity,
                "available": offering.is_visible and dish.is_active,
            }
        if lock:
            meal = (
                await self.session.execute(
                    select(MealSetOrm)
                    .where(MealSetOrm.id == item.meal_set_id)
                    .with_for_update(of=MealSetOrm)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
        else:
            meal = await self.session.get(MealSetOrm, item.meal_set_id, populate_existing=True)
        if meal is None:
            return None
        components = [dish_snapshot(c.dish) for c in meal.components]
        institution = await self.session.get(EducationInstitutionOrm, meal.institution_id)
        try:
            slot = cycle_slot(institution.cycle_start_monday, pickup_day())
        except ValueError:
            slot = None
        return {
            "item_type": "set",
            "meal_set_id": meal.id,
            "meal_type": meal.meal_type,
            "institution_id": meal.institution_id,
            "dish_name": meal.meal_type,
            "category": "set",
            "img_url": None,
            "fixed_price": meal.price,
            "components": components,
            **{
                key: sum(c[key] for c in components)
                for key in ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")
            },
            "available": slot == (meal.cycle_week, meal.weekday) and all(c.dish.is_active for c in meal.components),
        }

    async def add_typed(self, student_id, data, set_quantity=False):
        institution_id = await self.lock_student(student_id)
        basket = await self.get_by_student(student_id) or await self._create_basket(student_id)
        key = TypedCartItemOrm.buffet_offering_id if data.item_type == "buffet" else TypedCartItemOrm.meal_set_id
        item_id = data.buffet_offering_id if data.item_type == "buffet" else data.meal_set_id
        item = (
            await self.session.execute(
                select(TypedCartItemOrm).where(TypedCartItemOrm.cart_id == basket.id, key == item_id)
            )
        ).scalar_one_or_none()
        if set_quantity and data.cart_quantity == 0:
            if item is None:
                raise NotFoundError("Item not found")
            await self.session.delete(item)
            await self.session.commit()
            return
        candidate = item or TypedCartItemOrm(
            cart_id=basket.id,
            buffet_offering_id=data.buffet_offering_id,
            meal_set_id=data.meal_set_id,
            quantity=data.cart_quantity,
            pickup_date=pickup_day(),
            unit_price=1,
        )
        details = await self.typed_details(candidate)
        if not details or details["institution_id"] != institution_id or not details["available"]:
            raise NotFoundError("Item not found")
        quantity = data.cart_quantity if set_quantity else data.cart_quantity + (item.quantity if item else 0)
        if quantity < 1:
            raise BadRequestError("Quantity must be positive")
        if data.item_type == "set" and quantity != 1:
            raise BadRequestError("Only one of each set type is allowed")
        if data.item_type == "buffet" and quantity > details["schedule_quantity"]:
            raise BadRequestError("Insufficient stock")
        existing = await self.get_items(basket.id)
        others = [
            x
            for x in existing
            if not (
                x.get("item_type") == data.item_type
                and x.get("buffet_offering_id" if data.item_type == "buffet" else "meal_set_id") == item_id
            )
        ]
        if data.item_type == "set" and any(x.get("meal_type") == details["meal_type"] for x in others):
            raise BadRequestError("Only one of each set type is allowed")
        self.check_limits(
            sum(x["quantity"] for x in others),
            sum(x["total_price"] for x in others),
            quantity,
            quantity * details["fixed_price"],
        )
        candidate.quantity, candidate.unit_price, candidate.pickup_date = quantity, details["fixed_price"], pickup_day()
        if data.item_type == "set":
            candidate.material_snapshot = set_material(details)
        if item is None:
            self.session.add(candidate)
        basket.updated_at = now_local()
        await self.session.commit()

    async def remove_typed(self, student_id, item_type, item_id):
        await self.lock_student(student_id)
        basket = await self.get_by_student(student_id)
        if basket is None:
            raise NotFoundError("Basket not found")
        key = TypedCartItemOrm.buffet_offering_id if item_type == "buffet" else TypedCartItemOrm.meal_set_id
        result = await self.session.execute(
            delete(TypedCartItemOrm).where(TypedCartItemOrm.cart_id == basket.id, key == item_id)
        )
        if not result.rowcount:
            raise NotFoundError("Item not found")
        await self.session.commit()

    # ---- изменение ----
    async def add_dish(self, student_id: int, dish_id: int, quantity: int) -> None:
        if quantity <= 0:
            raise BadRequestError("Quantity must be positive")
        institution_id = await self.lock_student(student_id)
        schedule_dish = await self._get_tomorrow_schedule(dish_id, institution_id)
        basket = await self.get_by_student(student_id) or await self._create_basket(student_id)

        item = await self._get_item(basket.id, schedule_dish.id)
        new_quantity = (item.cart_quantity if item else 0) + quantity
        if new_quantity > schedule_dish.quantity:
            raise BadRequestError(
                f"Requested quantity ({new_quantity}) exceeds available quantity ({schedule_dish.quantity})"
            )

        total_dishes, total_amount = await self._totals(basket.id)
        self.check_limits(total_dishes, total_amount, quantity, schedule_dish.dish.fixed_price * quantity)

        if item:
            item.cart_quantity = new_quantity
        else:
            self.session.add(
                ShoppingCartDishesOrm(
                    shoppingcart_id=basket.id, schedule_dish_id=schedule_dish.id, cart_quantity=quantity
                )
            )
        basket.updated_at = now_local()
        await self.session.commit()

    async def set_quantity(self, student_id: int, dish_id: int, quantity: int) -> None:
        """Устанавливает количество блюда в корзине; 0 - удалить позицию."""
        if quantity < 0:
            raise BadRequestError("Quantity must not be negative")
        institution_id = await self.lock_student(student_id)
        schedule_dish = await self._get_tomorrow_schedule(dish_id, institution_id)
        basket = await self.get_by_student(student_id)
        if basket is None:
            raise NotFoundError("Cart not found")
        item = await self._get_item(basket.id, schedule_dish.id)
        if item is None:
            raise NotFoundError("Dish not found in cart")

        if quantity == 0:
            await self.session.delete(item)
        else:
            if quantity > schedule_dish.quantity:
                raise BadRequestError(
                    f"Requested quantity ({quantity}) exceeds available quantity ({schedule_dish.quantity})"
                )
            other_dishes, other_amount = await self._totals(basket.id, exclude_dish_id=dish_id)
            self.check_limits(other_dishes, other_amount, quantity, schedule_dish.dish.fixed_price * quantity)
            item.cart_quantity = quantity

        basket.updated_at = now_local()
        await self.session.commit()

    async def remove_dish(self, student_id: int, dish_id: int) -> None:
        await self.lock_student(student_id)
        basket = await self.get_by_student(student_id)
        if basket is None:
            raise NotFoundError("Basket not found")

        schedule_ids = select(ScheduleDishesOrm.id).where(ScheduleDishesOrm.dish_id == dish_id)
        result = await self.session.execute(
            delete(ShoppingCartDishesOrm).where(
                ShoppingCartDishesOrm.shoppingcart_id == basket.id,
                ShoppingCartDishesOrm.schedule_dish_id.in_(schedule_ids),
            )
        )
        if result.rowcount == 0:
            raise NotFoundError("Dish not found in basket")
        basket.updated_at = now_local()
        await self.session.commit()

    async def clear_stale_items(self) -> int:
        """Удаляет позиции корзин на уже наступившие даты (вызывается ночной задачей)."""
        stale_schedules = select(ScheduleDishesOrm.id).where(ScheduleDishesOrm.date <= today_local())
        affected_students = (
            select(ShoppingCartOrm.student_id)
            .join(ShoppingCartDishesOrm)
            .where(ShoppingCartDishesOrm.schedule_dish_id.in_(stale_schedules))
        )
        student_ids = list(
            (
                await self.session.execute(
                    select(StudentsOrm.id)
                    .where(StudentsOrm.id.in_(affected_students))
                    .order_by(StudentsOrm.id)
                    .with_for_update()
                )
            ).scalars()
        )
        locked_carts = select(ShoppingCartOrm.id).where(ShoppingCartOrm.student_id.in_(student_ids))
        result = await self.session.execute(
            delete(ShoppingCartDishesOrm).where(
                ShoppingCartDishesOrm.schedule_dish_id.in_(stale_schedules),
                ShoppingCartDishesOrm.shoppingcart_id.in_(locked_carts),
            )
        )
        await self.session.commit()
        return result.rowcount

    # ---- внутреннее ----
    async def lock_student(self, student_id: int) -> int:
        """Transaction lock shared by all cart writes, checkout and cancellation.

        Locking the student works even before their cart/first order exists.
        The caller must commit/rollback (or close the session) to release it.
        """
        query = (
            select(UsersOrm.institution_id)
            .join(StudentsOrm, StudentsOrm.user_id == UsersOrm.id)
            .where(StudentsOrm.id == student_id)
            .with_for_update(of=StudentsOrm)
        )
        institution_id = (await self.session.execute(query)).scalar_one_or_none()
        if institution_id is None:
            raise NotFoundError("Student not found")
        return institution_id

    async def _create_basket(self, student_id: int) -> ShoppingCartOrm:
        basket = ShoppingCartOrm(student_id=student_id)
        self.session.add(basket)
        await self.session.flush()
        return basket

    async def _get_tomorrow_schedule(self, dish_id: int, institution_id: int) -> ScheduleDishesOrm:
        query = (
            select(ScheduleDishesOrm)
            .options(selectinload(ScheduleDishesOrm.dish))
            .join(ScheduleDishesOrm.dish)
            .where(
                ScheduleDishesOrm.dish_id == dish_id,
                ScheduleDishesOrm.date == tomorrow_local(),
                DishesOrm.is_active.is_(True),
                DishesOrm.institution_id == institution_id,
            )
            .execution_options(populate_existing=True)
        )
        schedule_dish = (await self.session.execute(query)).scalar_one_or_none()
        if schedule_dish is None:
            raise NotFoundError("No schedule found for this dish")
        return schedule_dish

    async def _get_item(self, basket_id: int, schedule_dish_id: int) -> ShoppingCartDishesOrm | None:
        query = (
            select(ShoppingCartDishesOrm)
            .where(
                ShoppingCartDishesOrm.shoppingcart_id == basket_id,
                ShoppingCartDishesOrm.schedule_dish_id == schedule_dish_id,
            )
            .execution_options(populate_existing=True)
        )
        return (await self.session.execute(query)).scalar_one_or_none()

    async def _totals(self, basket_id: int, exclude_dish_id: int | None = None) -> tuple[int, int]:
        """(количество порций, сумма) в корзине, опционально без одного блюда."""
        query = (
            select(
                func.coalesce(func.sum(ShoppingCartDishesOrm.cart_quantity), 0),
                func.coalesce(func.sum(ShoppingCartDishesOrm.cart_quantity * DishesOrm.fixed_price), 0),
            )
            .select_from(ShoppingCartDishesOrm)
            .join(ShoppingCartDishesOrm.schedule_dish)
            .join(ScheduleDishesOrm.dish)
            .where(ShoppingCartDishesOrm.shoppingcart_id == basket_id)
        )
        if exclude_dish_id is not None:
            query = query.where(ScheduleDishesOrm.dish_id != exclude_dish_id)
        dishes, amount = (await self.session.execute(query)).one()
        return int(dishes), int(amount)

    def check_limits(self, current_dishes: int, current_amount: int, add_dishes: int, add_amount: int) -> None:
        if current_dishes + add_dishes > self.settings.max_cart_items:
            raise BadRequestError("Too many dishes")
        if current_amount + add_amount > self.settings.max_cart_amount:
            raise BadRequestError(
                f"Total order amount exceeds {self.settings.max_cart_amount}. "
                f"Current: {current_amount}, adding: {add_amount}"
            )
