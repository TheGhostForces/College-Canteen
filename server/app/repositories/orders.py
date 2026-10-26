import uuid
from datetime import date

from sqlalchemy import delete, extract, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.enums import OrderStatus
from app.db.models import (
    DishesOrm,
    OrderDishOrm,
    OrderOrm,
    ScheduleDishesOrm,
    ShoppingCartDishesOrm,
    ShoppingCartOrm,
)


class OrdersRepository:
    """Заказы. Заказ оформляется сегодня и выдаётся завтра (pickup_date)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- оформление и отмена ----
    async def create_from_basket(self, student_id: int) -> dict:
        active = await self.session.execute(
            select(OrderOrm.id).where(
                OrderOrm.student_id == student_id, OrderOrm.order_status == OrderStatus.IN_PROGRESS
            )
        )
        if active.first() is not None:
            raise BadRequestError("Order already exists")

        basket = (
            await self.session.execute(select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id))
        ).scalar_one_or_none()
        if basket is None:
            raise NotFoundError("Shopping cart not found")

        items = (
            (
                await self.session.execute(
                    select(ShoppingCartDishesOrm)
                    .options(selectinload(ShoppingCartDishesOrm.schedule_dish).selectinload(ScheduleDishesOrm.dish))
                    .where(ShoppingCartDishesOrm.shoppingcart_id == basket.id)
                )
            )
            .scalars()
            .all()
        )
        if not items:
            raise BadRequestError("Cart is empty")

        pickup_date = tomorrow_local()
        order_lines: list[dict] = []
        reserve: dict[int, int] = {}  # schedule_dish_id -> сколько порций списать
        to_remove: list[int] = []
        to_adjust: dict[int, int] = {}

        for item in items:
            schedule = item.schedule_dish
            if schedule.date != pickup_date or not schedule.dish.is_active or schedule.quantity <= 0:
                to_remove.append(item.id)
            elif item.cart_quantity > schedule.quantity:
                to_adjust[item.id] = schedule.quantity
            else:
                order_lines.append({"cart_quantity": item.cart_quantity, "dish_id": schedule.dish_id})
                reserve[schedule.id] = reserve.get(schedule.id, 0) + item.cart_quantity

        if to_adjust or to_remove:
            # корзину приводим в актуальное состояние, а студент подтверждает заказ повторно
            for item_id, quantity in to_adjust.items():
                await self.session.execute(
                    update(ShoppingCartDishesOrm)
                    .where(ShoppingCartDishesOrm.id == item_id)
                    .values(cart_quantity=quantity)
                )
            if to_remove:
                await self.session.execute(delete(ShoppingCartDishesOrm).where(ShoppingCartDishesOrm.id.in_(to_remove)))
            basket.updated_at = now_local()
            await self.session.commit()

            message = "Cart updated due to insufficient availability: "
            if to_adjust:
                message += f"quantities adjusted for {len(to_adjust)} items. "
            if to_remove:
                message += f"removed {len(to_remove)} unavailable items."
            raise BadRequestError(message.strip())

        if not order_lines:
            raise BadRequestError("No available dishes found in cart for tomorrow's order")

        order = OrderOrm(
            student_id=student_id,
            order_status=OrderStatus.IN_PROGRESS,
            order_number=f"TMP-{uuid.uuid4().hex}",  # заменяется ниже, когда известен id
            created_at=now_local(),
            pickup_date=pickup_date,
        )
        self.session.add(order)
        await self.session.flush()
        order.order_number = f"ORD-{1_000_000 + order.id}"

        await self.session.execute(insert(OrderDishOrm), [{**line, "order_id": order.id} for line in order_lines])

        # условное списание защищает от гонок: остаток не уйдёт в минус
        for schedule_id, quantity in reserve.items():
            result = await self.session.execute(
                update(ScheduleDishesOrm)
                .where(ScheduleDishesOrm.id == schedule_id, ScheduleDishesOrm.quantity >= quantity)
                .values(quantity=ScheduleDishesOrm.quantity - quantity)
            )
            if result.rowcount == 0:
                await self.session.rollback()
                raise BadRequestError(f"Not enough dishes available for schedule dish {schedule_id}")

        await self.session.execute(
            delete(ShoppingCartDishesOrm).where(ShoppingCartDishesOrm.shoppingcart_id == basket.id)
        )
        basket.updated_at = now_local()
        await self.session.commit()
        return {"order_number": order.order_number, "added_items": len(order_lines)}

    async def cancel_todays_order(self, student_id: int) -> None:
        """Отмена заказа, оформленного сегодня; порции возвращаются в остаток."""
        orders = (
            (
                await self.session.execute(
                    select(OrderOrm)
                    .where(
                        OrderOrm.student_id == student_id,
                        OrderOrm.order_status == OrderStatus.IN_PROGRESS,
                        OrderOrm.pickup_date == tomorrow_local(),
                    )
                    .options(selectinload(OrderOrm.order_dishes))
                )
            )
            .scalars()
            .all()
        )
        if not orders:
            raise NotFoundError("No order created today in progress found for this student")

        for order in orders:
            for line in order.order_dishes:
                await self.session.execute(
                    update(ScheduleDishesOrm)
                    .where(ScheduleDishesOrm.dish_id == line.dish_id, ScheduleDishesOrm.date == order.pickup_date)
                    .values(quantity=ScheduleDishesOrm.quantity + line.cart_quantity)
                )
            order.order_status = OrderStatus.CANCELLED
            order.updated_at = now_local()
        await self.session.commit()

    # ---- выдача ----
    async def complete_todays_orders(self, student_id: int) -> int:
        """Отмечает выданными заказы студента, которые нужно выдать сегодня. Возвращает их количество."""
        result = await self.session.execute(
            update(OrderOrm)
            .where(
                OrderOrm.student_id == student_id,
                OrderOrm.order_status == OrderStatus.IN_PROGRESS,
                OrderOrm.pickup_date == today_local(),
            )
            .values(order_status=OrderStatus.COMPLETED, updated_at=now_local())
        )
        await self.session.commit()
        return result.rowcount

    async def expire_overdue(self) -> int:
        """Невыданные заказы, день выдачи которых прошёл, становятся просроченными."""
        result = await self.session.execute(
            update(OrderOrm)
            .where(OrderOrm.order_status == OrderStatus.IN_PROGRESS, OrderOrm.pickup_date < today_local())
            .values(order_status=OrderStatus.EXPIRED, updated_at=now_local())
        )
        await self.session.commit()
        return result.rowcount

    # ---- чтение ----
    async def get_student_orders(self, student_id: int, pickup_date: date | None = None) -> dict[str, list[dict]]:
        """Активные заказы студента: {номер заказа: [позиции]}."""
        query = (
            select(OrderDishOrm)
            .join(OrderDishOrm.order)
            .options(selectinload(OrderDishOrm.dish), selectinload(OrderDishOrm.order))
            .where(OrderOrm.student_id == student_id, OrderOrm.order_status == OrderStatus.IN_PROGRESS)
            .order_by(OrderOrm.order_number, OrderDishOrm.id)
        )
        if pickup_date is not None:
            query = query.where(OrderOrm.pickup_date == pickup_date)

        orders: dict[str, list[dict]] = {}
        for line in (await self.session.execute(query)).scalars().all():
            orders.setdefault(line.order.order_number, []).append(
                {
                    "id": line.id,
                    "dish_id": line.dish_id,
                    "order_id": line.order_id,
                    "quantity": line.cart_quantity,
                    "dish_name": line.dish.dish_name,
                    "institution_id": line.dish.institution_id,
                    "category": line.dish.category,
                    "fixed_price": line.dish.fixed_price,
                    "total_price": line.cart_quantity * line.dish.fixed_price,
                    "img_url": line.dish.img_url,
                    "created_at": line.order.created_at,
                }
            )
        return orders

    async def get_institution_orders(
        self, institution_id: int, pickup_date: date | None = None
    ) -> dict[str, list[dict]]:
        """Активные заказы заведения: {номер заказа: [позиции]}; опционально - на конкретный день выдачи."""
        query = (
            select(
                OrderOrm.order_number,
                OrderOrm.created_at,
                OrderDishOrm.id,
                OrderDishOrm.cart_quantity,
                OrderDishOrm.order_id,
                OrderDishOrm.dish_id,
                DishesOrm.dish_name,
                DishesOrm.institution_id,
                DishesOrm.category,
                DishesOrm.fixed_price,
                DishesOrm.img_url,
            )
            .join(OrderDishOrm, OrderOrm.id == OrderDishOrm.order_id)
            .join(DishesOrm, OrderDishOrm.dish_id == DishesOrm.id)
            .where(OrderOrm.order_status == OrderStatus.IN_PROGRESS, DishesOrm.institution_id == institution_id)
            .order_by(OrderOrm.created_at.desc(), OrderOrm.order_number)
        )
        if pickup_date is not None:
            query = query.where(OrderOrm.pickup_date == pickup_date)

        orders: dict[str, list[dict]] = {}
        for row in (await self.session.execute(query)).all():
            orders.setdefault(row.order_number, []).append(
                {
                    "id": row.id,
                    "dish_id": row.dish_id,
                    "order_id": row.order_id,
                    "quantity": row.cart_quantity,
                    "dish_name": row.dish_name,
                    "institution_id": row.institution_id,
                    "category": row.category,
                    "fixed_price": row.fixed_price,
                    "total_price": row.cart_quantity * row.fixed_price,
                    "img_url": row.img_url,
                    "created_at": row.created_at,
                }
            )
        return orders

    async def get_ordered_totals(self, institution_id: int, day: date) -> list[dict]:
        """Сколько порций каждого блюда заказано на день - для поставщика."""
        query = (
            select(ScheduleDishesOrm)
            .join(DishesOrm)
            .where(ScheduleDishesOrm.date == day, DishesOrm.institution_id == institution_id)
            .options(joinedload(ScheduleDishesOrm.dish))
        )
        schedules = (await self.session.execute(query)).scalars().all()
        if not schedules:
            raise NotFoundError(f"No scheduled dishes found for date {day} and institution {institution_id}")
        return [
            {
                "id": s.id,
                "dish_id": s.dish_id,
                "institution_id": s.dish.institution_id,
                "dish_name": s.dish.dish_name,
                "category": s.dish.category,
                "total_quantity": s.total_quantity,
                "remains_quantity": s.quantity,
                "ordered_quantity": s.total_quantity - s.quantity,
                "fixed_price": s.dish.fixed_price,
                "date": day,
                "img_url": s.dish.img_url,
            }
            for s in schedules
        ]

    async def get_history(self, student_id: int, year: int, month: int) -> list[dict]:
        """Завершённые, отменённые и просроченные заказы студента за месяц."""
        query = (
            select(OrderOrm)
            .where(
                OrderOrm.student_id == student_id,
                OrderOrm.order_status != OrderStatus.IN_PROGRESS,
                extract("year", OrderOrm.updated_at) == year,
                extract("month", OrderOrm.updated_at) == month,
            )
            .options(selectinload(OrderOrm.order_dishes).selectinload(OrderDishOrm.dish))
            .order_by(OrderOrm.updated_at.desc())
        )
        return [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "order_status": order.order_status,
                "dishes": [
                    {
                        "dish_id": line.dish.id,
                        "quantity": line.cart_quantity,
                        "dish_name": line.dish.dish_name,
                        "fixed_price": line.dish.fixed_price,
                        "total_price": line.cart_quantity * line.dish.fixed_price,
                        "date": order.updated_at.date(),
                    }
                    for line in order.order_dishes
                ],
            }
            for order in (await self.session.execute(query)).scalars().all()
        ]
