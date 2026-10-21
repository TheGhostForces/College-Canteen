import hashlib
from datetime import timedelta, datetime, date
from typing import Optional, List
from fastapi import HTTPException
from sqlalchemy import select, update, delete, func, and_, extract, or_, exists
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload, joinedload
from database.db import new_session
from database.enums import StatusOrder
from database.models import StudentsOrm, TemporaryCodeOrm, DishesOrm, ShoppingCartOrm, ShoppingCartDishesOrm, OrderOrm, \
    OrderDishOrm, ScheduleDishesOrm, EducationInstitutionOrm, UsersOrm
from schemas import DishRequest, DishToBasket, DishUpdate, DishCreateList, UserSchema, StudentSchema


class UsersRepository:
    @classmethod
    async def get_user(cls, user_id: int = None, login: str = None, email: str = None):
        async with new_session() as session:
            query = select(UsersOrm)
            if user_id is not None:
                query = query.where(UsersOrm.id == user_id)
            if login is not None:
                query = query.where(UsersOrm.login == login)
            if email is not None:
                query = query.where(UsersOrm.email == email)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def get_student(cls, user_id: int = None, student_id: int = None):
        async with new_session() as session:
            query = select(StudentsOrm)
            if user_id is not None:
                query = query.where(StudentsOrm.user_id == user_id)
            if student_id is not None:
                query = query.where(StudentsOrm.id == student_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

class TemporaryCodeRepository:
    @classmethod
    async def set_temporary_code(cls, user_id: int, code: str):
        async with new_session() as session:
            code_hash = hashlib.sha256(code.encode()).hexdigest()

            now = datetime.now()
            expires_at = now + timedelta(minutes=10)

            temporary_code = TemporaryCodeOrm(
                code_hash=code_hash,
                attempts=0,
                created_at=now,
                expires_at=expires_at,
                used_at=None,
                user_id=user_id
            )

            session.add(temporary_code)
            await session.flush()
            await session.commit()
            return temporary_code

    @classmethod
    async def get_temporary_code(cls, user_id: int, temporary_code_id: int = None):
        async with new_session() as session:
            stmt = select(TemporaryCodeOrm).where(
                TemporaryCodeOrm.user_id == user_id,
                TemporaryCodeOrm.expires_at > datetime.now(),
                TemporaryCodeOrm.used_at == None
            )

            if temporary_code_id is not None:
                stmt = stmt.where(TemporaryCodeOrm.id == temporary_code_id)

            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @classmethod
    async def extend_expires_at(cls, temporary_code_id: int):
        async with new_session() as session:
            stmt = update(TemporaryCodeOrm).where(
                TemporaryCodeOrm.id == temporary_code_id
            ).values(expires_at=datetime.now() + timedelta(minutes=2))
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def increment_attempts(cls, temporary_code_id: int):
        async with new_session() as session:
            stmt = update(TemporaryCodeOrm).where(
                TemporaryCodeOrm.id == temporary_code_id
            ).values(attempts=TemporaryCodeOrm.attempts + 1)
            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def mark_code_as_used(cls, temporary_code_id: int):
        async with new_session() as session:
            stmt = update(TemporaryCodeOrm).where(
                TemporaryCodeOrm.id == temporary_code_id
            ).values(used_at=datetime.now())
            await session.execute(stmt)
            await session.commit()

class InstitutionRepository:
    @classmethod
    async def get_institutions(cls):
        async with new_session() as session:
            query = select(EducationInstitutionOrm)
            result = await session.execute(query)
            return result.scalars().all()

class DishesRepository:
    @classmethod
    async def get_dish(cls, dish_id: int = None, institution_id: int = None, dish_name: str = None):
        async with new_session() as session:
            query = select(DishesOrm)
            if dish_id is not None:
                query = query.where(DishesOrm.id == dish_id)
            if institution_id is not None:
                query = query.where(DishesOrm.institution_id == institution_id)
            if dish_name is not None:
                query = query.where(DishesOrm.dish_name == dish_name)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def delete_dishes(
            cls,
            institution_id: int,
            dish_ids: Optional[List[int]] = None,
            dish_names: Optional[List[str]] = None
    ):
        async with new_session() as session:
            try:
                if not dish_ids and not dish_names:
                    return 0, [], []

                not_found_ids = []
                not_found_names = []

                if dish_ids and len(dish_ids) > 0:
                    check_ids_query = select(DishesOrm.id).where(
                        and_(
                            DishesOrm.institution_id == institution_id,
                            DishesOrm.id.in_(dish_ids)
                        )
                    )
                    result = await session.execute(check_ids_query)
                    existing_ids = {row[0] for row in result.fetchall()}
                    not_found_ids = [did for did in dish_ids if did not in existing_ids]

                if dish_names and len(dish_names) > 0:
                    check_names_query = select(DishesOrm.dish_name).where(
                        and_(
                            DishesOrm.institution_id == institution_id,
                            DishesOrm.dish_name.in_(dish_names)
                        )
                    )
                    result = await session.execute(check_names_query)
                    existing_names = {row[0] for row in result.fetchall()}
                    not_found_names = [name for name in dish_names if name not in existing_names]

                if (dish_ids and len(dish_ids) == len(not_found_ids)) and \
                        (dish_names and len(dish_names) == len(not_found_names)):
                    return 0, not_found_ids, not_found_names

                update_query = update(DishesOrm).where(
                    DishesOrm.institution_id == institution_id
                ).values(is_active=False)

                conditions = []
                if dish_ids and len(dish_ids) > 0:
                    existing_ids_list = [did for did in dish_ids if did not in not_found_ids]
                    if existing_ids_list:
                        conditions.append(DishesOrm.id.in_(existing_ids_list))

                if dish_names and len(dish_names) > 0:
                    existing_names_list = [name for name in dish_names if name not in not_found_names]
                    if existing_names_list:
                        conditions.append(DishesOrm.dish_name.in_(existing_names_list))

                if conditions:
                    if len(conditions) > 1:
                        update_query = update_query.where(conditions[0] | conditions[1])
                    else:
                        update_query = update_query.where(conditions[0])

                    update_query = update_query.where(DishesOrm.is_active == True)

                    update_result = await session.execute(update_query)
                    await session.commit()
                    updated_count = update_result.rowcount

                    return updated_count, not_found_ids, not_found_names
                else:
                    await session.rollback()
                    return 0, not_found_ids, not_found_names

            except Exception as e:
                await session.rollback()
                print(f"Error deactivating dishes: {e}")
                return None

    @classmethod
    async def update_dish(cls, dish_id: int, data: DishUpdate):
        async with new_session() as session:
            try:
                update_data = {}

                if data.dish_name is not None:
                    update_data["dish_name"] = data.dish_name
                if data.category is not None:
                    update_data["category"] = data.category
                if data.fixed_price is not None:
                    update_data["fixed_price"] = data.fixed_price
                if data.img_url is not None:
                    update_data["img_url"] = data.img_url

                if not update_data:
                    return None

                query = update(DishesOrm).where(DishesOrm.id == dish_id).values(**update_data)

                await session.execute(query)
                await session.commit()

                result = await session.get(DishesOrm, dish_id)
                return result

            except Exception:
                await session.rollback()
                return None

    @classmethod
    async def get_dishes(cls,
                         dish_id: int = None,
                         institution_id: int = None,
                         dish_name: str = None,
                         category: str = None
):
        async with new_session() as session:
            query = select(DishesOrm).where(DishesOrm.is_active == True)
            if dish_id is not None:
                query = query.where(DishesOrm.id == dish_id)
            if institution_id is not None:
                query = query.where(DishesOrm.institution_id == institution_id)
            if dish_name is not None:
                query = query.where(DishesOrm.dish_name == dish_name)
            if category is not None:
                query = query.where(DishesOrm.category == category)
            result = await session.execute(query)
            return result.scalars().all()

    @classmethod
    async def get_dishes_on_next_day(cls, institution_id: int, next_day: date):
        async with new_session() as session:
            # Делаем LEFT JOIN от всех блюд к расписанию на нужную дату
            query = (
                select(DishesOrm, ScheduleDishesOrm)
                .outerjoin(
                    ScheduleDishesOrm,
                    (DishesOrm.id == ScheduleDishesOrm.dish_id) & (ScheduleDishesOrm.date == next_day)
                )
                .where(DishesOrm.institution_id == institution_id)
                .where(DishesOrm.is_active == True)  # опционально: только активные блюда
            )

            result = await session.execute(query)
            rows = result.all()

            formatted_result = []
            for dish, schedule in rows:
                formatted_result.append({
                    "id": schedule.id if schedule else None,  # id записи расписания (если есть)
                    "dish_id": dish.id,
                    "institution_id": dish.institution_id,
                    "dish_name": dish.dish_name,
                    "category": dish.category,
                    "quantity": schedule.quantity if schedule else 0,
                    "fixed_price": dish.fixed_price,
                    "img_url": dish.img_url,
                })
            return formatted_result

    @classmethod
    async def get_fixed_dishes_by_date(cls, institution_id: int, day: date):
        async with new_session() as session:
            query = (
                select(ScheduleDishesOrm)
                .join(DishesOrm)
                .where(
                    ScheduleDishesOrm.date == day,
                    DishesOrm.institution_id == institution_id
                )
                .options(joinedload(ScheduleDishesOrm.dish))
            )

            result = await session.execute(query)
            items = result.scalars().all()

            if not items:
                raise HTTPException(
                    status_code=404,
                    detail=f"Schedule not found for {day}"
                )

            formatted_result = []
            for item in items:
                formatted_result.append({
                    "id": item.id,
                    "dish_id": item.dish_id,
                    "institution_id": item.dish.institution_id,
                    "dish_name": item.dish.dish_name,
                    "category": item.dish.category,
                    "quantity": item.total_quantity,
                    "fixed_price": item.dish.fixed_price,
                    "img_url": item.dish.img_url,
                })
            return formatted_result

    @classmethod
    async def get_all_dishes_with_fixed_by_date(cls, institution_id: int, day: date):
        async with new_session() as session:
            query = (
                select(DishesOrm, ScheduleDishesOrm)
                .outerjoin(
                    ScheduleDishesOrm,
                    and_(
                        ScheduleDishesOrm.dish_id == DishesOrm.id,
                        ScheduleDishesOrm.date == day
                    )
                )
                .where(
                    DishesOrm.institution_id == institution_id,
                    DishesOrm.is_active == True
                )
                .order_by(DishesOrm.category, DishesOrm.dish_name)
            )

            result = await session.execute(query)
            rows = result.all()

            if not rows:
                raise HTTPException(
                    status_code=404,
                    detail=f"No active dishes found for institution {institution_id}"
                )

            formatted_result = []
            for dish, schedule_dish in rows:
                quantity = schedule_dish.quantity if schedule_dish else 0
                total_quantity = schedule_dish.total_quantity if schedule_dish else 0

                formatted_result.append({
                    "dish_id": dish.id,
                    "dish_name": dish.dish_name,
                    "category": dish.category,
                    "quantity": quantity,
                    "total_quantity": total_quantity,
                    "fixed_price": dish.fixed_price,
                    "img_url": dish.img_url,
                })
            return formatted_result


    @classmethod
    async def create_many_dishes(cls, institution_id: int, data: DishCreateList):
        async with new_session() as session:
            dish_names = [item.dish_name.strip() for item in data.items if item.dish_name]
            if not dish_names:
                raise HTTPException(
                    status_code=400,
                    detail="No dish names provided"
                )

            existing_dishes = await session.execute(
                select(DishesOrm.dish_name).where(
                    DishesOrm.dish_name.in_(dish_names),
                    DishesOrm.institution_id == institution_id
                )
            )
            existing_dish_names = {dish_name for (dish_name,) in existing_dishes}

            dishes_to_insert = []
            duplicate_names = []

            for item in data.items:
                dish_name = item.dish_name.strip()
                if not dish_name:
                    continue

                if dish_name in existing_dish_names:
                    duplicate_names.append(dish_name)
                else:
                    dish_data = item.model_dump()
                    dish_data["institution_id"] = institution_id
                    dishes_to_insert.append(dish_data)
                    existing_dish_names.add(dish_name)

            if not dishes_to_insert:
                if duplicate_names:
                    raise HTTPException(
                        status_code=400,
                        detail=f"All dishes already exist: {', '.join(duplicate_names)}"
                    )
                raise HTTPException(
                    status_code=400,
                    detail="No valid dishes to add"
                )

            result = await session.execute(
                insert(DishesOrm).returning(DishesOrm.id),
                dishes_to_insert
            )
            created_dish_ids = result.scalars().all()

            await session.commit()

            response_data = {
                "created_dish_ids": created_dish_ids,
                "created_count": len(created_dish_ids),
            }

            if duplicate_names:
                response_data["duplicate_dishes"] = duplicate_names
                response_data["duplicate_count"] = len(duplicate_names)

            return response_data

    @classmethod
    async def set_dishes_on_day(cls, institution_id: int, data: DishRequest, target_date: date):
        async with new_session() as session:
            dish_ids = [item.dish_id for item in data.items]

            existing_dishes = await session.execute(
                select(DishesOrm.id).where(
                    DishesOrm.id.in_(dish_ids),
                    DishesOrm.institution_id == institution_id,
                    DishesOrm.is_active == True
                )
            )
            existing_dish_ids = {dish_id for (dish_id,) in existing_dishes}

            invalid_dish_ids = set(dish_ids) - existing_dish_ids
            if invalid_dish_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"Incorrect any dish for institution or inactive" # добавить конкртеное обозначение из-за чего ошибка
                )

            for item in data.items:
                existing_schedule = await session.execute(
                    select(ScheduleDishesOrm).where(
                        ScheduleDishesOrm.dish_id == item.dish_id,
                        ScheduleDishesOrm.date == target_date
                    )
                )
                existing_schedule = existing_schedule.scalar_one_or_none()

                if existing_schedule:
                    existing_schedule.quantity = item.cart_quantity
                    existing_schedule.total_quantity = item.cart_quantity
                else:
                    schedule_dish = ScheduleDishesOrm(
                        date=target_date,
                        dish_id=item.dish_id,
                        quantity=item.cart_quantity,
                        total_quantity=item.cart_quantity,
                    )
                    session.add(schedule_dish)

            await session.commit()

    @classmethod
    async def change_remaining_by_id(cls, dish_id: int, quantity: int):
        async with new_session() as session:
            stmt = update(DishesOrm).where(
                DishesOrm.id == dish_id
            ).values(quantity=quantity)
            await session.execute(stmt)
            await session.commit()

class StudentBasketRepository:
    @classmethod
    async def get_basket_by_student_id(cls, student_id: int):
        async with new_session() as session:
            query = select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def create_student_basket(cls, student_id: int):
        async with new_session() as session:
            query = ShoppingCartOrm(student_id=student_id)
            session.add(query)
            await session.flush()
            await session.commit()
            return query.id

class BasketDishesRepository:
    @classmethod
    async def get_basket(cls, basket_id: int = None, student_id: int = None):
        async with new_session() as session:
            query = select(ShoppingCartOrm)
            if basket_id is not None:
                query = query.where(ShoppingCartOrm.id == basket_id)
            if student_id is not None:
                query = query.where(ShoppingCartOrm.student_id == student_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @classmethod
    async def get_dishes(cls, id_basket: int = None, shoppingcart_id: int = None, schedule_dish_id: int = None):
        async with new_session() as session:
            query = select(ShoppingCartDishesOrm).options(
                selectinload(ShoppingCartDishesOrm.schedule_dish).selectinload(ScheduleDishesOrm.dish)
            )
            if id_basket is not None:
                query = query.where(ShoppingCartDishesOrm.id == id_basket)
            if shoppingcart_id is not None:
                query = query.where(ShoppingCartDishesOrm.shoppingcart_id == shoppingcart_id)
            if schedule_dish_id is not None:
                query = query.where(ShoppingCartDishesOrm.schedule_dish_id == schedule_dish_id)

            result = await session.execute(query)
            cart_items = result.scalars().all()

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
                for item in cart_items
            ]

    @classmethod
    async def add_dish_to_basket(cls, student_id: int, data: DishToBasket):
        async with new_session() as session:
            schedule_query = select(ScheduleDishesOrm).options(
                selectinload(ScheduleDishesOrm.dish)
            ).join(
                ScheduleDishesOrm.dish
            ).where(
                and_(
                    ScheduleDishesOrm.dish_id == data.dish_id,
                    ScheduleDishesOrm.date == date.today() + timedelta(days=1)
                )
            )
            schedule_result = await session.execute(schedule_query)
            schedule_dish = schedule_result.scalar_one_or_none()

            if not schedule_dish:
                raise HTTPException(status_code=404, detail="No schedule found for this dish")

            if data.cart_quantity > schedule_dish.quantity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Requested quantity ({data.cart_quantity}) exceeds available quantity ({schedule_dish.quantity})"
                )

            dish_price = schedule_dish.dish.fixed_price

            query = select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id)
            result = await session.execute(query)
            shopping_cart = result.scalar_one_or_none()

            if not shopping_cart:
                shopping_cart = ShoppingCartOrm(student_id=student_id)
                session.add(shopping_cart)
                await session.flush()

            query = select(
                func.sum(ShoppingCartDishesOrm.cart_quantity),
                func.sum(ShoppingCartDishesOrm.cart_quantity * DishesOrm.fixed_price)
            ).select_from(ShoppingCartDishesOrm).join(
                ShoppingCartDishesOrm.schedule_dish
            ).join(
                ScheduleDishesOrm.dish
            ).where(
                ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id
            )
            result = await session.execute(query)
            total_info = result.first()
            total_dishes = total_info[0] or 0
            total_amount = total_info[1] or 0

            if total_dishes + data.cart_quantity > 5:
                raise HTTPException(status_code=400, detail="Too many dishes")

            new_item_amount = dish_price * data.cart_quantity
            if total_amount + new_item_amount > 1000:
                raise HTTPException(
                    status_code=400,
                    detail=f"Total order amount exceeds 1000. Current: {total_amount}, adding: {new_item_amount}"
                )

            query = select(ShoppingCartDishesOrm).where(
                and_(
                    ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                    ShoppingCartDishesOrm.schedule_dish_id == schedule_dish.id
                )
            )
            result = await session.execute(query)
            existing_item = result.scalar_one_or_none()

            if existing_item:
                new_quantity = existing_item.cart_quantity + data.cart_quantity

                if total_dishes + data.cart_quantity > 5:
                    raise HTTPException(status_code=400, detail="Too many dishes")
                if total_amount + new_item_amount > 1000:
                    raise HTTPException(status_code=400, detail="Total order amount exceeds 1000")

                existing_item.cart_quantity = new_quantity
            else:
                dish_basket = ShoppingCartDishesOrm(
                    shoppingcart_id=shopping_cart.id,
                    schedule_dish_id=schedule_dish.id,
                    cart_quantity=data.cart_quantity
                )
                session.add(dish_basket)

            stmt = update(
                ShoppingCartOrm
            ).where(
                ShoppingCartOrm.student_id == student_id
            ).values(updated_at=datetime.now())
            await session.execute(stmt)

            await session.commit()

    @classmethod
    async def delete_dish_from_basket(cls, student_id: int, dish_id: int):
        async with new_session() as session:
            query = select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id)
            result = await session.execute(query)
            shopping_cart = result.scalar_one_or_none()

            if not shopping_cart:
                raise HTTPException(status_code=404, detail="Basket not found")

            query = select(ShoppingCartDishesOrm).options(
                selectinload(ShoppingCartDishesOrm.schedule_dish)
            ).where(
                and_(
                    ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                    ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id == dish_id)
                )
            )
            result = await session.execute(query)
            cart_item = result.scalar_one_or_none()

            if not cart_item:
                raise HTTPException(status_code=404, detail="Dish not found in basket")

            stmt = delete(
                ShoppingCartDishesOrm
            ).where(
                and_(
                    ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                    ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id == dish_id)
                )
            )

            result = await session.execute(stmt)

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Dish not found in basket")

            stmt = update(
                ShoppingCartOrm
            ).where(
                ShoppingCartOrm.student_id == student_id
            ).values(updated_at=datetime.now())

            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def change_quantity(cls, student_id: int, data: DishToBasket):
        async with new_session() as session:
            schedule_query = select(ScheduleDishesOrm).options(
                selectinload(ScheduleDishesOrm.dish)
            ).join(
                ScheduleDishesOrm.dish
            ).where(
                and_(
                    ScheduleDishesOrm.dish_id == data.dish_id,
                    ScheduleDishesOrm.date == date.today() + timedelta(days=1)
                )
            )
            schedule_result = await session.execute(schedule_query)
            schedule_dish = schedule_result.scalar_one_or_none()

            if not schedule_dish:
                raise HTTPException(status_code=404, detail="No schedule found for this dish")

            dish_price = schedule_dish.dish.fixed_price

            query = select(ShoppingCartOrm).where(ShoppingCartOrm.student_id == student_id)
            result = await session.execute(query)
            shopping_cart = result.scalar_one_or_none()

            if not shopping_cart:
                raise HTTPException(status_code=404, detail="Cart not found")

            query = select(ShoppingCartDishesOrm).where(
                and_(
                    ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                    ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id == data.dish_id)
                )
            )
            result = await session.execute(query)
            cart_item = result.scalar_one_or_none()

            if not cart_item:
                raise HTTPException(status_code=404, detail="Dish not found in cart")

            query = select(
                func.sum(ShoppingCartDishesOrm.cart_quantity),
                func.sum(ShoppingCartDishesOrm.cart_quantity * DishesOrm.fixed_price)
            ).select_from(ShoppingCartDishesOrm).join(
                ShoppingCartDishesOrm.schedule_dish
            ).join(
                ScheduleDishesOrm.dish
            ).where(
                and_(
                    ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                    ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id != data.dish_id)
                )
            )
            result = await session.execute(query)
            other_dishes_info = result.first()
            other_dishes_total = other_dishes_info[0] or 0
            other_dishes_amount = other_dishes_info[1] or 0

            if other_dishes_total + data.cart_quantity > 5:
                raise HTTPException(status_code=400, detail="Too many dishes")

            new_item_amount = dish_price * data.cart_quantity
            if other_dishes_amount + new_item_amount > 1000:
                raise HTTPException(
                    status_code=400,
                    detail=f"Total order amount exceeds 1000. Current: {other_dishes_amount}, new item: {new_item_amount}"
                )

            if data.cart_quantity == 0:
                stmt = delete(
                    ShoppingCartDishesOrm
                ).where(
                    and_(
                        ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                        ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id == data.dish_id)
                    )
                )
                await session.execute(stmt)
            else:
                stmt = update(
                    ShoppingCartDishesOrm
                ).where(
                    and_(
                        ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id,
                        ShoppingCartDishesOrm.schedule_dish.has(ScheduleDishesOrm.dish_id == data.dish_id)
                    )
                ).values(cart_quantity=data.cart_quantity)

                await session.execute(stmt)

            stmt = update(
                ShoppingCartOrm
            ).where(
                ShoppingCartOrm.student_id == student_id
            ).values(updated_at=datetime.now())

            await session.execute(stmt)
            await session.commit()

    @classmethod
    async def expired_all_orders_and_clear_all_baskets(cls):
        async with new_session() as session:
            query = update(OrderOrm).where(
                OrderOrm.order_status == StatusOrder.IN_PROGRESS,
                OrderOrm.created_at <= datetime.now() - timedelta(days=1)
            ).values(
                order_status=StatusOrder.EXPIRED,
                updated_at=datetime.now()
            )
            result = await session.execute(query)
            expired_count = result.rowcount

            query = delete(ShoppingCartDishesOrm)
            result = await session.execute(query)
            baskets_count = result.rowcount

            print(f"[{datetime.now()}] Произошла очистка: "
                  f"истекло {expired_count} заказов, "
                  f"очищено {baskets_count} блюд из корзин")

            await session.commit()

class OrdersRepository:
    @classmethod
    async def create_order(cls, student_id: int):
        async with new_session() as session:
            query = select(OrderOrm).where(
                OrderOrm.student_id == student_id
            ).where(
                OrderOrm.order_status == StatusOrder.IN_PROGRESS
            )
            result = await session.execute(query)
            order = result.scalar_one_or_none()
            if order:
                raise HTTPException(status_code=400, detail="Order already exists")

            cart_query = select(ShoppingCartOrm).where(
                ShoppingCartOrm.student_id == student_id
            )
            cart_result = await session.execute(cart_query)
            shopping_cart = cart_result.scalar_one_or_none()

            if not shopping_cart:
                raise HTTPException(status_code=404, detail="Shopping cart not found")

            stmt = select(ShoppingCartDishesOrm).options(
                selectinload(ShoppingCartDishesOrm.schedule_dish)
            ).where(
                ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id
            )
            result = await session.execute(stmt)
            cart_items = result.scalars().all()

            if not cart_items:
                raise HTTPException(status_code=400, detail="Cart is empty")

            order_dish_data = []
            schedule_updates = {}
            cart_updates = {}
            items_to_remove = []

            for cart_item in cart_items:
                if cart_item.schedule_dish.date != date.today() + timedelta(days=1):
                    items_to_remove.append(cart_item.id)
                    continue

                available_quantity = cart_item.schedule_dish.quantity
                requested_quantity = cart_item.cart_quantity

                if available_quantity <= 0:
                    items_to_remove.append(cart_item.id)
                    continue

                if requested_quantity > available_quantity:
                    cart_updates[cart_item.id] = available_quantity
                    continue

                order_dish_data.append({
                    'cart_quantity': requested_quantity,
                    'dish_id': cart_item.schedule_dish.dish_id,
                    'order_id': None,
                })

                schedule_dish_id = cart_item.schedule_dish.id
                schedule_updates[schedule_dish_id] = schedule_updates.get(schedule_dish_id, 0) + requested_quantity

            if cart_updates or items_to_remove:
                for cart_item_id, new_quantity in cart_updates.items():
                    stmt = update(ShoppingCartDishesOrm).where(
                        ShoppingCartDishesOrm.id == cart_item_id
                    ).values(cart_quantity=new_quantity)
                    await session.execute(stmt)

                if items_to_remove:
                    stmt = delete(ShoppingCartDishesOrm).where(
                        ShoppingCartDishesOrm.id.in_(items_to_remove)
                    )
                    await session.execute(stmt)

                update_cart_stmt = update(ShoppingCartOrm).where(
                    ShoppingCartOrm.id == shopping_cart.id
                ).values(updated_at=datetime.now())
                await session.execute(update_cart_stmt)

                await session.commit()

                error_message = "Cart updated due to insufficient availability: "
                if cart_updates:
                    error_message += f"quantities adjusted for {len(cart_updates)} items. "
                if items_to_remove:
                    error_message += f"removed {len(items_to_remove)} unavailable items."

                raise HTTPException(
                    status_code=400,
                    detail=error_message.strip()
                )

            if not order_dish_data:
                raise HTTPException(
                    status_code=400,
                    detail="No available dishes found in cart for tomorrow's order"
                )

            import time
            import random
            timestamp = int(time.time() * 1000)
            random_part = random.randint(1000, 9999)
            temp_order_number = f"ORD-{timestamp}-{random_part}"

            order = OrderOrm(
                student_id=student_id,
                order_status=StatusOrder.IN_PROGRESS,
                order_number=temp_order_number,
                created_at=datetime.now(),
            )
            session.add(order)
            await session.flush()

            order.order_number = f"ORD-{1000000 + order.id}"

            for dish_data in order_dish_data:
                dish_data['order_id'] = order.id

            stmt = insert(OrderDishOrm).values(order_dish_data)
            await session.execute(stmt)

            for schedule_dish_id, quantity_to_subtract in schedule_updates.items():
                stmt = update(ScheduleDishesOrm).where(
                    and_(
                        ScheduleDishesOrm.id == schedule_dish_id,
                        ScheduleDishesOrm.quantity >= quantity_to_subtract
                    )
                ).values(quantity=ScheduleDishesOrm.quantity - quantity_to_subtract)

                result = await session.execute(stmt)

                if result.rowcount == 0:
                    await session.rollback()
                    raise HTTPException(
                        status_code=400,
                        detail=f"Not enough dishes available for schedule dish {schedule_dish_id}"
                    )

            delete_stmt = delete(ShoppingCartDishesOrm).where(
                ShoppingCartDishesOrm.shoppingcart_id == shopping_cart.id
            )
            await session.execute(delete_stmt)

            update_cart_stmt = update(ShoppingCartOrm).where(
                ShoppingCartOrm.id == shopping_cart.id
            ).values(updated_at=datetime.now())
            await session.execute(update_cart_stmt)

            await session.commit()

            return {
                "order_id": order.id,
                "order_number": order.order_number,
                "added_items": len(order_dish_data),
            }

    @classmethod
    async def get_dishes(cls, order_id: int = None, student_id: int = None, dish_id: int = None):
        async with new_session() as session:
            # if student_id is not None:
            #     student = await session.get(StudentsOrm, student_id)
            #     if not student:
            #         raise HTTPException(status_code=404, detail="Student not found")
            # переделать

            query = select(OrderDishOrm).options(
                selectinload(OrderDishOrm.dish),
                selectinload(OrderDishOrm.order)
            )

            query = query.join(OrderDishOrm.order).where(OrderOrm.order_status == StatusOrder.IN_PROGRESS)

            if order_id is not None:
                query = query.where(OrderDishOrm.order_id == order_id)
            if student_id is not None:
                query = query.where(OrderOrm.student_id == student_id)
            if dish_id is not None:
                query = query.where(OrderDishOrm.dish_id == dish_id)

            query = query.order_by(OrderOrm.order_number, OrderDishOrm.id)

            result = await session.execute(query)
            order_items = result.scalars().all()

            orders_dict = {}

            for item in order_items:
                order_number = item.order.order_number

                if order_number not in orders_dict:
                    orders_dict[order_number] = []

                orders_dict[order_number].append({
                    "id": item.id,
                    "dish_id": item.dish_id,
                    "order_id": item.order_id,
                    "quantity": item.cart_quantity,
                    "dish_name": item.dish.dish_name,
                    "institution_id": item.dish.institution_id,
                    "category": item.dish.category,
                    "fixed_price": item.dish.fixed_price,
                    "total_price": item.cart_quantity * item.dish.fixed_price,
                    "img_url": item.dish.img_url,
                    "created_at": item.order.created_at,
                })

            return orders_dict

    @classmethod
    async def complete_order(cls, student_id: int):
        async with (new_session() as session):
            if student_id is not None:
                student = await session.get(StudentsOrm, student_id)
                if not student:
                    raise HTTPException(status_code=404, detail="Student not found")

            query = update(
                OrderOrm
            ).where(
                OrderOrm.student_id == student_id
            ).where(
                OrderOrm.order_status == StatusOrder.IN_PROGRESS
            ).values(
                order_status=StatusOrder.COMPLETED,
                updated_at=datetime.now(),
            )
            await session.execute(query)
            await session.commit()

    @classmethod
    async def undo_order(cls, student_id: int):
        async with new_session() as session:
            today = date.today()

            query = (
                select(OrderOrm)
                .where(
                    OrderOrm.student_id == student_id,
                    OrderOrm.order_status == StatusOrder.IN_PROGRESS,
                    OrderOrm.created_at >= today  # Добавляем условие: заказ создан сегодня
                )
            )
            result = await session.execute(query)
            orders = result.scalars().all()

            if not orders:
                raise ValueError("No order created today in progress found for this student")

            tomorrow = today + timedelta(days=1)

            for order in orders:
                query_dishes = (
                    select(OrderDishOrm)
                    .where(OrderDishOrm.order_id == order.id)
                )
                result_dishes = await session.execute(query_dishes)
                order_dishes = result_dishes.scalars().all()

                for order_dish in order_dishes:
                    stmt = update(ScheduleDishesOrm).where(
                        ScheduleDishesOrm.dish_id == order_dish.dish_id,
                        ScheduleDishesOrm.date == tomorrow
                    ).values(
                        quantity=ScheduleDishesOrm.quantity + order_dish.cart_quantity
                    )
                    await session.execute(stmt)

                query_update = (
                    update(OrderOrm)
                    .where(OrderOrm.id == order.id)
                    .values(
                        order_status=StatusOrder.CANCELLED,
                        updated_at=datetime.now()
                    )
                )
                await session.execute(query_update)

            await session.commit()

    @classmethod
    async def get_all_ordered_dishes(cls, institution_id: int, day: date):
        async with new_session() as session:
            query = (
                select(ScheduleDishesOrm)
                .join(DishesOrm)
                .where(
                    ScheduleDishesOrm.date == day,
                    DishesOrm.institution_id == institution_id
                )
                .options(joinedload(ScheduleDishesOrm.dish))
            )

            result = await session.execute(query)
            schedule_dishes = result.scalars().all()

            if not schedule_dishes:
                raise HTTPException(
                    status_code=404,
                    detail=f"No scheduled dishes found for date {day} and institution {institution_id}"
                )

            formatted_result = []
            for schedule_dish in schedule_dishes:
                formatted_result.append({
                    "id": schedule_dish.id,
                    "dish_id": schedule_dish.dish_id,
                    "institution_id": schedule_dish.dish.institution_id,
                    "dish_name": schedule_dish.dish.dish_name,
                    "category": schedule_dish.dish.category,
                    "total_quantity": schedule_dish.total_quantity,
                    "remains_quantity": schedule_dish.quantity,
                    "ordered_quantity": schedule_dish.total_quantity - schedule_dish.quantity,
                    "fixed_price": schedule_dish.dish.fixed_price,
                    "date": day,
                    "img_url": schedule_dish.dish.img_url,
                })
            return formatted_result

    @classmethod
    async def get_orders_with_dishes(cls, institution_id: int, target_date: date = None):
        async with new_session() as session:
            query = select(
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
                DishesOrm.img_url
            ).join(
                OrderDishOrm, OrderOrm.id == OrderDishOrm.order_id
            ).join(
                DishesOrm, OrderDishOrm.dish_id == DishesOrm.id
            ).order_by(
                OrderOrm.created_at.desc(),
                OrderOrm.order_number
            )

            if target_date is not None:
                query = query.where(
                and_(
                    OrderOrm.order_status == StatusOrder.IN_PROGRESS,
                    DishesOrm.institution_id == institution_id,
                    func.date(OrderOrm.created_at) == target_date
                )
                )
            else:
                query = query.where(
                and_(
                    OrderOrm.order_status == StatusOrder.IN_PROGRESS,
                    DishesOrm.institution_id == institution_id
                )
                )

            result = await session.execute(query)
            rows = result.all()

            orders_dict = {}

            for row in rows:
                order_number = row.order_number
                total_price = row.cart_quantity * row.fixed_price

                item_data = {
                    "id": row.id,
                    "dish_id": row.dish_id,
                    "order_id": row.order_id,
                    "quantity": row.cart_quantity,
                    "dish_name": row.dish_name,
                    "institution_id": row.institution_id,
                    "category": row.category,
                    "fixed_price": row.fixed_price,
                    "total_price": total_price,
                    "img_url": row.img_url,
                    "created_at": row.created_at
                }

                if order_number not in orders_dict:
                    orders_dict[order_number] = []

                orders_dict[order_number].append(item_data)

            return orders_dict

class HistoryRepository:
    @classmethod
    async def get_history_for_month(cls, student_id: int, month: int = None, year: int = None):
        async with new_session() as session:
            if month is None or year is None:
                current_date = datetime.now()
                year = current_date.year
                month = current_date.month

            query = select(OrderOrm).where(
                OrderOrm.student_id == student_id
            ).where(
                and_(
                    extract('year', OrderOrm.updated_at) == year,
                    extract('month', OrderOrm.updated_at) == month,
                )
            ).options(
            selectinload(OrderOrm.order_dishes).options(
                selectinload(OrderDishOrm.dish)
            ),
        )
            result = await session.execute(query)
            order_items = result.scalars().all()

        return [
            {
                "order_id": order.id,
                "order_number": order.order_number,
                "order_status": order.order_status,
                "dishes": [
                    {
                        "dish_id": order_dish.dish.id,
                        "quantity": order_dish.cart_quantity,
                        "dish_name": order_dish.dish.dish_name,
                        "fixed_price": order_dish.dish.fixed_price,
                        "total_price": order_dish.cart_quantity * order_dish.dish.fixed_price,
                        "date": order.updated_at.date(),
                    }
                    for order_dish in order.order_dishes
                ]
            }
            for order in order_items
        ]

class AdminRepository:
    @classmethod
    async def add_client(cls, user: UserSchema, student: StudentSchema = None):
        async with new_session() as session:
            exists_query = select(exists().where(
            or_(
                UsersOrm.login == user.login,
                UsersOrm.email == user.email
            )
        ))
            result = await session.execute(exists_query)
            existing_user = result.scalar_one_or_none()

            if existing_user:
                raise HTTPException(status_code=409, detail=f"User with login '{user.login}' or email '{user.email}' already exists")

            user_orm = UsersOrm(
                login=user.login,
                email=user.email,
                role=user.role.value,
                institution_id=user.institution_id
            )
            if student is not None and user.role.value == "student":
                student_orm = StudentsOrm(
                    full_name=student.full_name,
                    date_start=student.date_start,
                    date_end=student.date_end,
                    user=user_orm
                )

            session.add(user_orm)

            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
