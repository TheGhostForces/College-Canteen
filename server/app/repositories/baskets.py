from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.models import DishesOrm, ScheduleDishesOrm, ShoppingCartDishesOrm, ShoppingCartOrm


class BasketRepository:
    """Корзина студента. Корзина всегда собирается на завтрашний день."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    # ---- чтение ----
    async def get_by_student(self, student_id: int) -> ShoppingCartOrm | None:
        query = select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id)
        return (await self.session.execute(query)).scalar_one_or_none()

    async def create_for_student(self, student_id: int) -> ShoppingCartOrm:
        basket = ShoppingCartOrm(student_id=student_id)
        self.session.add(basket)
        await self.session.commit()
        return basket

    async def get_items(self, basket_id: int) -> list[dict]:
        query = (
            select(ShoppingCartDishesOrm)
            .options(selectinload(ShoppingCartDishesOrm.schedule_dish).selectinload(ScheduleDishesOrm.dish))
            .where(ShoppingCartDishesOrm.shoppingcart_id == basket_id)
        )
        items = (await self.session.execute(query)).scalars().all()
        return [
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

    # ---- изменение ----
    async def add_dish(self, student_id: int, dish_id: int, quantity: int) -> None:
        schedule_dish = await self._get_tomorrow_schedule(dish_id)
        basket = await self.get_by_student(student_id) or await self._create_basket(student_id)

        item = await self._get_item(basket.id, schedule_dish.id)
        new_quantity = (item.cart_quantity if item else 0) + quantity
        if new_quantity > schedule_dish.quantity:
            raise BadRequestError(
                f"Requested quantity ({new_quantity}) exceeds available quantity ({schedule_dish.quantity})"
            )

        total_dishes, total_amount = await self._totals(basket.id)
        self._check_limits(total_dishes, total_amount, quantity, schedule_dish.dish.fixed_price * quantity)

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
        schedule_dish = await self._get_tomorrow_schedule(dish_id)
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
            self._check_limits(other_dishes, other_amount, quantity, schedule_dish.dish.fixed_price * quantity)
            item.cart_quantity = quantity

        basket.updated_at = now_local()
        await self.session.commit()

    async def remove_dish(self, student_id: int, dish_id: int) -> None:
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
        result = await self.session.execute(
            delete(ShoppingCartDishesOrm).where(ShoppingCartDishesOrm.schedule_dish_id.in_(stale_schedules))
        )
        await self.session.commit()
        return result.rowcount

    # ---- внутреннее ----
    async def _create_basket(self, student_id: int) -> ShoppingCartOrm:
        basket = ShoppingCartOrm(student_id=student_id)
        self.session.add(basket)
        await self.session.flush()
        return basket

    async def _get_tomorrow_schedule(self, dish_id: int) -> ScheduleDishesOrm:
        query = (
            select(ScheduleDishesOrm)
            .options(selectinload(ScheduleDishesOrm.dish))
            .join(ScheduleDishesOrm.dish)
            .where(
                ScheduleDishesOrm.dish_id == dish_id,
                ScheduleDishesOrm.date == tomorrow_local(),
                DishesOrm.is_active.is_(True),
            )
        )
        schedule_dish = (await self.session.execute(query)).scalar_one_or_none()
        if schedule_dish is None:
            raise NotFoundError("No schedule found for this dish")
        return schedule_dish

    async def _get_item(self, basket_id: int, schedule_dish_id: int) -> ShoppingCartDishesOrm | None:
        query = select(ShoppingCartDishesOrm).where(
            ShoppingCartDishesOrm.shoppingcart_id == basket_id,
            ShoppingCartDishesOrm.schedule_dish_id == schedule_dish_id,
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

    def _check_limits(self, current_dishes: int, current_amount: int, add_dishes: int, add_amount: int) -> None:
        if current_dishes + add_dishes > self.settings.max_cart_items:
            raise BadRequestError("Too many dishes")
        if current_amount + add_amount > self.settings.max_cart_amount:
            raise BadRequestError(
                f"Total order amount exceeds {self.settings.max_cart_amount}. "
                f"Current: {current_amount}, adding: {add_amount}"
            )
