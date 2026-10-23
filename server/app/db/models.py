from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, Enum, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import OrderStatus


class UsersOrm(Base):
    __tablename__ = "Users"

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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(nullable=False)
    group_name: Mapped[str] = mapped_column(nullable=False)
    date_start: Mapped[date] = mapped_column(Date, nullable=False)
    date_end: Mapped[date] = mapped_column(Date, nullable=False)
    rating: Mapped[int] = mapped_column(default=0, nullable=False)

    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id", ondelete="CASCADE"), unique=True, nullable=False)

    shopping_carts: Mapped[list["ShoppingCartOrm"]] = relationship("ShoppingCartOrm", back_populates="student")
    orders: Mapped[list["OrderOrm"]] = relationship("OrderOrm", back_populates="student")

    user: Mapped["UsersOrm"] = relationship("UsersOrm", back_populates="student")


class TemporaryCodeOrm(Base):
    __tablename__ = "TemporaryCode"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code_hash: Mapped[str] = mapped_column(nullable=False)
    attempts: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    used_at: Mapped[datetime] = mapped_column(nullable=True)

    user_id: Mapped[int] = mapped_column(ForeignKey("Users.id"), nullable=False, index=True)
    user: Mapped["UsersOrm"] = relationship("UsersOrm", back_populates="temporary_codes")


class EducationInstitutionOrm(Base):
    __tablename__ = "EducationInstitution"

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
    # Вес
    # Пищевые ценности
    fixed_price: Mapped[int] = mapped_column(nullable=False)
    img_url: Mapped[str] = mapped_column(nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default=text("true"))

    institution_id: Mapped[int] = mapped_column(ForeignKey("EducationInstitution.id"), nullable=False)

    institution: Mapped["EducationInstitutionOrm"] = relationship("EducationInstitutionOrm", back_populates="dishes")
    order_items: Mapped[list["OrderDishOrm"]] = relationship("OrderDishOrm", back_populates="dish")
    schedules: Mapped[list["ScheduleDishesOrm"]] = relationship("ScheduleDishesOrm", back_populates="dish")

    __table_args__ = (UniqueConstraint("institution_id", "dish_name", name="uq_dish_institution_name"),)


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

    __table_args__ = (UniqueConstraint("dish_id", "date", name="uq_dish_date"),)


class ShoppingCartOrm(Base):
    __tablename__ = "ShoppingCart"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    updated_at: Mapped[datetime] = mapped_column(nullable=True)

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

    __table_args__ = (UniqueConstraint("shoppingcart_id", "schedule_dish_id", name="uq_cart_schedule_dish"),)


class OrderOrm(Base):
    __tablename__ = "Order"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_number: Mapped[str] = mapped_column(nullable=False, unique=True, index=True)
    order_status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)
    # День выдачи. Раньше выводился из created_at + 1 день, что ломало границы суток.
    pickup_date: Mapped[date] = mapped_column(Date, nullable=False)

    student_id: Mapped[int] = mapped_column(ForeignKey("Students.id"), nullable=False)
    student: Mapped["StudentsOrm"] = relationship("StudentsOrm", back_populates="orders")
    order_dishes: Mapped[list["OrderDishOrm"]] = relationship("OrderDishOrm", back_populates="order")

    __table_args__ = (
        Index("ix_order_student_status", "student_id", "order_status"),
        Index("ix_order_status_pickup_date", "order_status", "pickup_date"),
    )


class OrderDishOrm(Base):
    __tablename__ = "OrderDish"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cart_quantity: Mapped[int] = mapped_column(nullable=False)

    order_id: Mapped[int] = mapped_column(ForeignKey("Order.id"), nullable=False, index=True)
    dish_id: Mapped[int] = mapped_column(ForeignKey("Dishes.id"), nullable=False)

    order: Mapped["OrderOrm"] = relationship("OrderOrm", back_populates="order_dishes")
    dish: Mapped["DishesOrm"] = relationship("DishesOrm", back_populates="order_items")
