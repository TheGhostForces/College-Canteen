import json
import uuid
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import delete, extract, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.config import get_settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.timeutils import now_local, today_local, tomorrow_local
from app.db.enums import OrderStatus
from app.db.models import (
    BuffetOfferingOrm,
    DishesOrm,
    OrderDishOrm,
    OrderOrm,
    ScheduleDishesOrm,
    ShoppingCartDishesOrm,
    ShoppingCartOrm,
    TypedCartItemOrm,
    TypedOrderItemOrm,
)
from app.repositories.baskets import BasketRepository, set_material
from app.services.menu_calendar import next_pickup_day, ordering_open


def menu_now():
    return datetime.now(UTC)


class OrdersRepository:
    """Заказы. Заказ оформляется сегодня и выдаётся завтра (pickup_date)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_supplier_report(self, institution_id: int, pickup_date: date) -> dict:
        lines = (await self.session.execute(
            select(TypedOrderItemOrm)
            .join(OrderOrm, TypedOrderItemOrm.order_id == OrderOrm.id)
            .where(
                OrderOrm.institution_id == institution_id,
                OrderOrm.pickup_date == pickup_date,
                OrderOrm.order_status != OrderStatus.CANCELLED,
            )
            .order_by(TypedOrderItemOrm.id)
        )).scalars().all()
        sets, buffet = {}, {}
        for line in lines:
            if line.item_type == "set":
                components = line.snapshot.get("components", [])
                key = (line.meal_set_id, line.meal_type, json.dumps(components, sort_keys=True, ensure_ascii=False))
                entry = sets.setdefault(key, {
                    "meal_set_id": line.meal_set_id, "meal_type": line.meal_type,
                    "quantity": 0, "components": components,
                })
            elif line.item_type == "buffet":
                key = line.buffet_offering_id
                entry = buffet.setdefault(key, {
                    "buffet_offering_id": key, "dish_name": line.snapshot.get("dish_name", ""), "quantity": 0,
                })
            else:
                continue
            entry["quantity"] += line.quantity
        return {"sets": list(sets.values()), "buffet": list(buffet.values())}

    # ---- оформление и отмена ----
    async def create_from_basket(self, student_id: int, *, allow_legacy: bool = False) -> dict:
        basket_repo = BasketRepository(self.session)
        institution_id = await basket_repo.lock_student(student_id)
        typed_cart_id = (
            await self.session.execute(select(ShoppingCartOrm.id).where(ShoppingCartOrm.student_id == student_id))
        ).scalar_one_or_none()
        if typed_cart_id is not None:
            if not allow_legacy:
                removed = await self.session.execute(
                    delete(ShoppingCartDishesOrm).where(ShoppingCartDishesOrm.shoppingcart_id == typed_cart_id)
                )
                if removed.rowcount:
                    await self.session.commit()
                    raise BadRequestError("Cart updated; scheduled dishes are no longer sold")
            typed_items = (
                (
                    await self.session.execute(
                        select(TypedCartItemOrm)
                        .where(TypedCartItemOrm.cart_id == typed_cart_id)
                        # Every checkout locks buffet rows by ID first, then set rows by ID.
                        # Cancellation also locks buffet rows by ascending ID; set edits
                        # lock only their own set row.
                        .order_by(
                            TypedCartItemOrm.buffet_offering_id.asc().nulls_last(),
                            TypedCartItemOrm.meal_set_id.asc().nulls_last(),
                            TypedCartItemOrm.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if typed_items:
                return await self.create_typed_order(student_id, institution_id, typed_cart_id, typed_items)
        if not allow_legacy:
            raise BadRequestError("Cart is empty")
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
                    .where(ShoppingCartDishesOrm.shoppingcart_id == basket.id)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if not items:
            raise BadRequestError("Cart is empty")

        pickup_date = tomorrow_local()
        # Stable lock order avoids deadlocks between students buying the same
        # dishes. Refresh after waiting: stock may have changed while blocked.
        schedules = (
            (
                await self.session.execute(
                    select(ScheduleDishesOrm)
                    .where(ScheduleDishesOrm.id.in_([item.schedule_dish_id for item in items]))
                    .options(joinedload(ScheduleDishesOrm.dish))
                    .order_by(ScheduleDishesOrm.id)
                    .with_for_update(of=ScheduleDishesOrm)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        schedule_by_id = {schedule.id: schedule for schedule in schedules}
        if any(schedule.dish.institution_id != institution_id for schedule in schedules):
            raise BadRequestError("This dish does not belong to this student")
        order_lines: list[dict] = []
        reserve: dict[int, int] = {}  # schedule_dish_id -> сколько порций списать
        to_remove: list[int] = []
        to_adjust: dict[int, int] = {}

        for item in items:
            schedule = schedule_by_id[item.schedule_dish_id]
            if schedule.date != pickup_date or not schedule.dish.is_active or schedule.quantity <= 0:
                to_remove.append(item.id)
            elif item.cart_quantity > schedule.quantity:
                to_adjust[item.id] = schedule.quantity
            else:
                order_lines.append(
                    {
                        "cart_quantity": item.cart_quantity,
                        "dish_id": schedule.dish_id,
                        "unit_price": schedule.dish.fixed_price,
                    }
                )
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

        # Цены и лимиты могли измениться после добавления блюда в корзину.
        basket_repo.check_limits(
            0,
            0,
            sum(line["cart_quantity"] for line in order_lines),
            sum(line["cart_quantity"] * line["unit_price"] for line in order_lines),
        )

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
        for schedule_id, quantity in sorted(reserve.items()):
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

    async def create_typed_order(self, student_id, institution_id, cart_id, items):
        timezone = ZoneInfo(get_settings().timezone)
        pickup = next_pickup_day(menu_now(), timezone)
        if not ordering_open(menu_now(), pickup, timezone):
            raise BadRequestError("Ordering closed")
        repo = BasketRepository(self.session)
        lines = []
        changed = False
        meal_types = set()
        previous = set(
            (
                await self.session.execute(
                    select(TypedOrderItemOrm.meal_type)
                    .join(OrderOrm, TypedOrderItemOrm.order_id == OrderOrm.id)
                    .where(
                        OrderOrm.student_id == student_id,
                        OrderOrm.pickup_date == pickup,
                        OrderOrm.order_status != OrderStatus.CANCELLED,
                        TypedOrderItemOrm.item_type == "set",
                    )
                )
            ).scalars()
        )
        for item in items:
            details = await repo.typed_details(item, lock=True)
            if not details or details["institution_id"] != institution_id or not details["available"]:
                await self.session.delete(item)
                changed = True
                continue
            if item.buffet_offering_id and details["schedule_quantity"] < item.quantity:
                if details["schedule_quantity"] == 0:
                    await self.session.delete(item)
                    changed = True
                    continue
                item.quantity = details["schedule_quantity"]
                changed = True
            if item.pickup_date != pickup or item.unit_price != details["fixed_price"]:
                item.pickup_date, item.unit_price = pickup, details["fixed_price"]
                changed = True
            if item.meal_set_id is not None:
                material = set_material(details)
                if item.material_snapshot != material:
                    item.material_snapshot = material
                    changed = True
                if item.quantity != 1 or details["meal_type"] in meal_types or details["meal_type"] in previous:
                    raise BadRequestError("Only one of each set type per pickup day")
                meal_types.add(details["meal_type"])
            lines.append((item, details))
        if changed:
            await self.session.commit()
            raise BadRequestError("Cart updated; please confirm again")
        repo.check_limits(
            0,
            0,
            sum(item.quantity for item, _ in lines),
            sum(item.quantity * details["fixed_price"] for item, details in lines),
        )
        order = OrderOrm(
            student_id=student_id,
            institution_id=institution_id,
            order_status=OrderStatus.IN_PROGRESS,
            order_number=f"TMP-{uuid.uuid4().hex}",
            created_at=now_local(),
            pickup_date=pickup,
        )
        self.session.add(order)
        await self.session.flush()
        order.order_number = f"ORD-{1_000_000 + order.id}"
        for item, details in lines:
            if item.buffet_offering_id is not None:
                offering = await self.session.get(BuffetOfferingOrm, item.buffet_offering_id)
                offering.quantity -= item.quantity
            snapshot = {k: v for k, v in details.items() if k not in ("available", "schedule_quantity")}
            self.session.add(
                TypedOrderItemOrm(
                    order_id=order.id,
                    buffet_offering_id=item.buffet_offering_id,
                    meal_set_id=item.meal_set_id,
                    item_type=details["item_type"],
                    meal_type=details.get("meal_type"),
                    quantity=item.quantity,
                    unit_price=details["fixed_price"],
                    snapshot=snapshot,
                )
            )
            await self.session.delete(item)
        await self.session.commit()
        return {"order_number": order.order_number, "added_items": len(lines)}

    async def cancel_todays_order(self, student_id: int, legacy_now=None) -> None:
        """Отмена заказа, оформленного сегодня; порции возвращаются в остаток."""
        await BasketRepository(self.session).lock_student(student_id)
        orders = (
            (
                await self.session.execute(
                    select(OrderOrm)
                    .where(
                        OrderOrm.student_id == student_id,
                        OrderOrm.order_status == OrderStatus.IN_PROGRESS,
                        OrderOrm.pickup_date.in_(
                            [tomorrow_local(), next_pickup_day(menu_now(), ZoneInfo(get_settings().timezone))]
                        ),
                    )
                    .options(selectinload(OrderOrm.order_dishes))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        if not orders:
            raise NotFoundError("No order created today in progress found for this student")

        quantities_by_offering = {}
        for order in orders:
            typed_lines = (
                (await self.session.execute(select(TypedOrderItemOrm).where(TypedOrderItemOrm.order_id == order.id)))
                .scalars()
                .all()
            )
            if typed_lines and not ordering_open(menu_now(), order.pickup_date, ZoneInfo(get_settings().timezone)):
                raise BadRequestError("Not enough time")
            if (
                not typed_lines
                and legacy_now is not None
                and legacy_now.hour >= get_settings().order_cancel_deadline_hour
            ):
                raise BadRequestError("Not enough time")
            for line in typed_lines:
                if line.buffet_offering_id is not None:
                    quantities_by_offering[line.buffet_offering_id] = (
                        quantities_by_offering.get(line.buffet_offering_id, 0) + line.quantity
                    )
        # Lock all offerings in the same order as checkout, across all orders.
        # Per-order lock ordering can deadlock when two students bought the same
        # offerings in opposite order across multiple transactions.
        offerings = (
            (
                await self.session.execute(
                    select(BuffetOfferingOrm)
                    .where(BuffetOfferingOrm.id.in_(quantities_by_offering))
                    .order_by(BuffetOfferingOrm.id)
                    .with_for_update(of=BuffetOfferingOrm)
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .all()
        )
        for offering in offerings:
            offering.quantity += quantities_by_offering[offering.id]
        for order in orders:
            schedules = (
                (
                    await self.session.execute(
                        select(ScheduleDishesOrm)
                        .where(
                            ScheduleDishesOrm.dish_id.in_([line.dish_id for line in order.order_dishes]),
                            ScheduleDishesOrm.date == order.pickup_date,
                        )
                        .order_by(ScheduleDishesOrm.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                )
                .scalars()
                .all()
            )
            quantities: dict[int, int] = {}
            for line in order.order_dishes:
                quantities[line.dish_id] = quantities.get(line.dish_id, 0) + line.cart_quantity
            for schedule in schedules:
                schedule.quantity += quantities[schedule.dish_id]
            order.order_status = OrderStatus.CANCELLED
            order.updated_at = now_local()
        await self.session.commit()

    # ---- выдача ----
    async def complete_todays_orders(self, student_id: int, institution_id: int) -> int:
        """Отмечает выданными заказы студента, которые нужно выдать сегодня. Возвращает их количество."""
        result = await self.session.execute(
            update(OrderOrm)
            .where(
                OrderOrm.student_id == student_id,
                OrderOrm.institution_id == institution_id,
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
    async def get_student_orders(
        self, student_id: int, pickup_date: date | None = None, institution_id: int | None = None
    ) -> dict[str, list[dict]]:
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
        if institution_id is not None:
            query = query.where(OrderOrm.institution_id == institution_id)

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
                    "fixed_price": line.unit_price,
                    "total_price": line.cart_quantity * line.unit_price,
                    "img_url": line.dish.img_url,
                    "created_at": line.order.created_at,
                }
            )
        await self._append_typed_orders(
            orders, student_id=student_id, institution_id=institution_id, pickup_date=pickup_date
        )
        return orders

    async def _append_typed_orders(self, orders, student_id=None, institution_id=None, pickup_date=None):
        query = (
            select(TypedOrderItemOrm, OrderOrm)
            .join(OrderOrm, TypedOrderItemOrm.order_id == OrderOrm.id)
            .where(OrderOrm.order_status == OrderStatus.IN_PROGRESS)
        )
        if student_id is not None:
            query = query.where(OrderOrm.student_id == student_id)
        if pickup_date is not None:
            query = query.where(OrderOrm.pickup_date == pickup_date)
        if institution_id is not None:
            query = query.where(OrderOrm.institution_id == institution_id)
        for line, order in (await self.session.execute(query.order_by(OrderOrm.id, TypedOrderItemOrm.id))).all():
            if institution_id is not None and line.snapshot["institution_id"] != institution_id:
                continue
            orders.setdefault(order.order_number, []).append(
                {
                    **line.snapshot,
                    "id": line.id,
                    "order_id": order.id,
                    "quantity": line.quantity,
                    "fixed_price": line.unit_price,
                    "total_price": line.quantity * line.unit_price,
                    "created_at": order.created_at,
                    "pickup_date": order.pickup_date,
                }
            )

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
                OrderDishOrm.unit_price,
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
                    "fixed_price": row.unit_price,
                    "total_price": row.cart_quantity * row.unit_price,
                    "img_url": row.img_url,
                    "created_at": row.created_at,
                }
            )
        await self._append_typed_orders(orders, institution_id=institution_id, pickup_date=pickup_date)
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
        history = [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "order_status": order.order_status,
                "dishes": [
                    {
                        "dish_id": line.dish.id,
                        "quantity": line.cart_quantity,
                        "dish_name": line.dish.dish_name,
                        "fixed_price": line.unit_price,
                        "total_price": line.cart_quantity * line.unit_price,
                        "date": order.updated_at.date(),
                    }
                    for line in order.order_dishes
                ],
            }
            for order in (await self.session.execute(query)).scalars().all()
        ]
        by_id = {entry["order_id"]: entry for entry in history}
        if by_id:
            typed = (
                (await self.session.execute(select(TypedOrderItemOrm).where(TypedOrderItemOrm.order_id.in_(by_id))))
                .scalars()
                .all()
            )
            for line in typed:
                entry = by_id[line.order_id]
                order = await self.session.get(OrderOrm, line.order_id)
                entry["dishes"].append(
                    {
                        **line.snapshot,
                        "quantity": line.quantity,
                        "fixed_price": line.unit_price,
                        "total_price": line.quantity * line.unit_price,
                        "date": order.updated_at.date(),
                    }
                )
        return history
