from datetime import date, datetime
from typing import Optional

from sqlalchemy import JSON, CheckConstraint, Date, Enum, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import OrderStatus


class UsersOrm(Base):
    __tablename__ = "Users"

    __table_args__ = (
        CheckConstraint("role IN ('student', 'provider', 'operator', 'admin')", name="ck_users_role"),
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(nullable=False, unique=True)
    role: Mapped[str] = mapped_column(nullable=False)

    institution_id: Mapped[int] = mapped_column(ForeignKey("EducationInstitution.id"), nullable=False, index=True)

    institution: Mapped["EducationInstitutionOrm"] = relationship("EducationInstitutionOrm", back_populates="user")
    temporary_codes: Mapped[list["TemporaryCodeOrm"]] = relationship("TemporaryCodeOrm", back_populates="user")
    student: Mapped[Optional["StudentsOrm"]] = relationship(
        "StudentsOrm", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class StudentsOrm(Base):
    __tablename__ = "Students"
    __table_args__ = (CheckConstraint("study_end_year >= study_start_year", name="ck_students_years"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(nullable=False)
    group_name: Mapped[str] = mapped_column(nullable=False)
    study_start_year: Mapped[int] = mapped_column(nullable=False)
    study_end_year: Mapped[int] = mapped_column(nullable=False)
    rating: Mapped[int] = mapped_column(default=0, nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id", ondelete="CASCADE"), unique=True, nullable=False)

    shopping_carts: Mapped[list["ShoppingCartOrm"]] = relationship("ShoppingCartOrm", back_populates="student")
    orders: Mapped[list["OrderOrm"]] = relationship("OrderOrm", back_populates="student")

    user: Mapped["UsersOrm"] = relationship("UsersOrm", back_populates="student")


class TemporaryCodeOrm(Base):
    __tablename__ = "TemporaryCode"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_temporary_code_attempts"),
        CheckConstraint("expires_at > created_at", name="ck_temporary_code_dates"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id"), nullable=False, index=True)
    user: Mapped["UsersOrm"] = relationship("UsersOrm", back_populates="temporary_codes")


class EducationInstitutionOrm(Base):
    __tablename__ = "EducationInstitution"
    __table_args__ = (
        CheckConstraint("EXTRACT(ISODOW FROM cycle_start_monday) = 1", name="ck_institution_cycle_monday"),
    )

    cycle_start_monday: Mapped[date | None] = mapped_column(Date, nullable=True)
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(nullable=False)
    # адрес

    user: Mapped[list["UsersOrm"]] = relationship("UsersOrm", back_populates="institution")
    dishes: Mapped[list["DishesOrm"]] = relationship("DishesOrm", back_populates="institution")


class DishesOrm(Base):
    __tablename__ = "Dishes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    dish_name: Mapped[str] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(nullable=False)
    serving_weight_g: Mapped[float] = mapped_column(nullable=False, default=0, server_default=text("0"))
    energy_kcal: Mapped[float] = mapped_column(nullable=False, default=0, server_default=text("0"))
    protein_g: Mapped[float] = mapped_column(nullable=False, default=0, server_default=text("0"))
    fat_g: Mapped[float] = mapped_column(nullable=False, default=0, server_default=text("0"))
    carbohydrates_g: Mapped[float] = mapped_column(nullable=False, default=0, server_default=text("0"))
    fixed_price: Mapped[int] = mapped_column(nullable=False)
    img_url: Mapped[str | None] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))

    institution_id: Mapped[int] = mapped_column(ForeignKey("EducationInstitution.id"), nullable=False)

    institution: Mapped["EducationInstitutionOrm"] = relationship("EducationInstitutionOrm", back_populates="dishes")
    order_items: Mapped[list["OrderDishOrm"]] = relationship("OrderDishOrm", back_populates="dish")
    schedules: Mapped[list["ScheduleDishesOrm"]] = relationship("ScheduleDishesOrm", back_populates="dish")

    __table_args__ = (
        UniqueConstraint("institution_id", "dish_name", name="uq_dish_institution_name"),
        CheckConstraint("fixed_price > 0", name="ck_dishes_price"),
        CheckConstraint("length(trim(category)) > 0", name="ck_dishes_category"),
        CheckConstraint(
            "serving_weight_g >= 0 AND energy_kcal >= 0 AND protein_g >= 0 AND fat_g >= 0 AND carbohydrates_g >= 0",
            name="ck_dishes_nutrition",
        ),
    )


class MealSetOrm(Base):
    __tablename__ = "MealSet"
    __table_args__ = (
        UniqueConstraint("institution_id", "cycle_week", "weekday", "meal_type", name="uq_meal_set_slot"),
        CheckConstraint("cycle_week IN (1, 2)", name="ck_meal_set_week"),
        CheckConstraint("weekday BETWEEN 0 AND 4", name="ck_meal_set_weekday"),
        CheckConstraint("meal_type IN ('breakfast', 'lunch', 'afternoon_snack', 'dinner')", name="ck_meal_set_type"),
        CheckConstraint("price > 0 AND price <= 100000", name="ck_meal_set_price"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    institution_id: Mapped[int] = mapped_column(ForeignKey("EducationInstitution.id"), nullable=False)
    cycle_week: Mapped[int] = mapped_column(nullable=False)
    weekday: Mapped[int] = mapped_column(nullable=False)
    meal_type: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(nullable=False)
    components: Mapped[list["MealSetComponentOrm"]] = relationship(
        cascade="all, delete-orphan", order_by="MealSetComponentOrm.position", lazy="selectin"
    )


class MealSetComponentOrm(Base):
    __tablename__ = "MealSetComponent"
    __table_args__ = (UniqueConstraint("meal_set_id", "dish_id", name="uq_meal_set_component"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    meal_set_id: Mapped[int] = mapped_column(ForeignKey("MealSet.id", ondelete="CASCADE"), nullable=False)
    dish_id: Mapped[int] = mapped_column(ForeignKey("Dishes.id"), nullable=False)
    position: Mapped[int] = mapped_column(nullable=False)
    dish: Mapped["DishesOrm"] = relationship(lazy="joined")


class BuffetOfferingOrm(Base):
    __tablename__ = "BuffetOffering"
    __table_args__ = (
        UniqueConstraint("dish_id", name="uq_buffet_dish"),
        CheckConstraint("quantity >= 0", name="ck_buffet_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("Dishes.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    is_visible: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))
    dish: Mapped["DishesOrm"] = relationship(lazy="joined")


class ScheduleDishesOrm(Base):
    __tablename__ = "ScheduleDishes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    total_quantity: Mapped[int] = mapped_column(nullable=False)

    dish_id: Mapped[int] = mapped_column(ForeignKey("Dishes.id"), nullable=False)

    dish: Mapped["DishesOrm"] = relationship("DishesOrm", back_populates="schedules")
    cart_items: Mapped[list["ShoppingCartDishesOrm"]] = relationship(
        "ShoppingCartDishesOrm", back_populates="schedule_dish"
    )

    __table_args__ = (
        UniqueConstraint("dish_id", "date", name="uq_dish_date"),
        CheckConstraint("quantity >= 0 AND total_quantity >= quantity", name="ck_schedule_quantities"),
    )


class ShoppingCartOrm(Base):
    __tablename__ = "ShoppingCart"
    __table_args__ = (UniqueConstraint("student_id", name="uq_cart_student"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("Students.id"), nullable=False)
    student: Mapped["StudentsOrm"] = relationship("StudentsOrm", back_populates="shopping_carts")
    cart_dishes: Mapped[list["ShoppingCartDishesOrm"]] = relationship(
        "ShoppingCartDishesOrm", back_populates="shopping_cart"
    )


class ShoppingCartDishesOrm(Base):
    __tablename__ = "ShoppingCartDishes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cart_quantity: Mapped[int] = mapped_column(nullable=False)

    shoppingcart_id: Mapped[int] = mapped_column(ForeignKey("ShoppingCart.id"), nullable=False)
    schedule_dish_id: Mapped[int] = mapped_column(ForeignKey("ScheduleDishes.id"), nullable=False)

    shopping_cart: Mapped["ShoppingCartOrm"] = relationship("ShoppingCartOrm", back_populates="cart_dishes")
    schedule_dish: Mapped["ScheduleDishesOrm"] = relationship("ScheduleDishesOrm", back_populates="cart_items")

    __table_args__ = (
        UniqueConstraint("shoppingcart_id", "schedule_dish_id", name="uq_cart_schedule_dish"),
        CheckConstraint("cart_quantity > 0", name="ck_cart_dishes_quantity"),
    )


class TypedCartItemOrm(Base):
    __tablename__ = "TypedCartItem"
    __table_args__ = (
        CheckConstraint("quantity > 0 AND unit_price > 0", name="ck_typed_cart_quantity"),
        CheckConstraint(
            "(buffet_offering_id IS NOT NULL)::int + (meal_set_id IS NOT NULL)::int = 1", name="ck_typed_cart_kind"
        ),
        UniqueConstraint("cart_id", "buffet_offering_id", name="uq_typed_cart_buffet"),
        UniqueConstraint("cart_id", "meal_set_id", name="uq_typed_cart_set"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    cart_id: Mapped[int] = mapped_column(ForeignKey("ShoppingCart.id", ondelete="CASCADE"), nullable=False)
    buffet_offering_id: Mapped[int | None] = mapped_column(ForeignKey("BuffetOffering.id"))
    meal_set_id: Mapped[int | None] = mapped_column(nullable=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)
    unit_price: Mapped[int] = mapped_column(nullable=False)
    material_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class TypedOrderItemOrm(Base):
    __tablename__ = "TypedOrderItem"
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_price > 0", name="ck_typed_order_values"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("Order.id"), nullable=False, index=True)
    buffet_offering_id: Mapped[int | None] = mapped_column(ForeignKey("BuffetOffering.id"))
    meal_set_id: Mapped[int | None] = mapped_column(nullable=True)
    item_type: Mapped[str] = mapped_column(nullable=False)
    meal_type: Mapped[str | None] = mapped_column(nullable=True)
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)


class OrderOrm(Base):
    __tablename__ = "Order"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(nullable=False, unique=True, index=True)
    order_status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    # День выдачи. Раньше выводился из created_at + 1 день, что ломало границы суток.
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)
    institution_id: Mapped[int | None] = mapped_column(ForeignKey("EducationInstitution.id"), nullable=True)

    student_id: Mapped[int] = mapped_column(ForeignKey("Students.id"), nullable=False)
    student: Mapped["StudentsOrm"] = relationship("StudentsOrm", back_populates="orders")
    order_dishes: Mapped[list["OrderDishOrm"]] = relationship("OrderDishOrm", back_populates="order")

    __table_args__ = (
        Index("ix_order_student_status", "student_id", "order_status"),
        Index("ix_order_status_pickup_date", "order_status", "pickup_date"),
    )


class OrderDishOrm(Base):
    __tablename__ = "OrderDish"
    __table_args__ = (
        CheckConstraint("cart_quantity > 0", name="ck_order_dishes_quantity"),
        CheckConstraint("unit_price > 0", name="ck_order_dishes_price"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cart_quantity: Mapped[int] = mapped_column(nullable=False)

    # Цена на момент оформления: изменение каталога не переписывает историю.
    unit_price: Mapped[int] = mapped_column(nullable=False)

    order_id: Mapped[int] = mapped_column(ForeignKey("Order.id"), nullable=False, index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("Dishes.id"), nullable=False)

    order: Mapped["OrderOrm"] = relationship("OrderOrm", back_populates="order_dishes")
    dish: Mapped["DishesOrm"] = relationship("DishesOrm", back_populates="order_items")
