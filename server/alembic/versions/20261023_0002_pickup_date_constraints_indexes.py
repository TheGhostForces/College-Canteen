"""День выдачи заказа, уникальные ограничения и индексы.

- Order.pickup_date: раньше день выдачи выводился из created_at + 1 день (ломалось на границе суток).
  Для существующих заказов заполняется как created_at::date + 1.
- Уникальность блюда в заведении и позиции в корзине. Уже существующие дубликаты предварительно
  устраняются: у блюд дубликаты получают суффикс " #<id>", дубликаты позиций корзины удаляются.
- Dishes.is_active: NOT NULL (NULL трактуется как true), по умолчанию true.
- Индексы по внешним ключам и колонкам, по которым идут выборки.
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- блюда ---
    op.execute('UPDATE "Dishes" SET is_active = TRUE WHERE is_active IS NULL')
    op.alter_column("Dishes", "is_active", existing_type=sa.Boolean(), nullable=False, server_default=sa.text("true"))
    op.execute(
        """
        UPDATE "Dishes" SET dish_name = dish_name || ' #' || id
        WHERE id NOT IN (SELECT MIN(id) FROM "Dishes" GROUP BY institution_id, dish_name)
        """
    )
    op.create_unique_constraint("uq_dish_institution_name", "Dishes", ["institution_id", "dish_name"])

    # --- корзина ---
    op.execute(
        """
        DELETE FROM "ShoppingCartDishes"
        WHERE id NOT IN (SELECT MIN(id) FROM "ShoppingCartDishes" GROUP BY shoppingcart_id, schedule_dish_id)
        """
    )
    op.create_unique_constraint("uq_cart_schedule_dish", "ShoppingCartDishes", ["shoppingcart_id", "schedule_dish_id"])

    # --- заказы ---
    op.add_column("Order", sa.Column("pickup_date", sa.Date(), nullable=True))
    op.execute('UPDATE "Order" SET pickup_date = created_at::date + 1')
    op.alter_column("Order", "pickup_date", existing_type=sa.Date(), nullable=False)
    op.create_index("ix_order_status_pickup_date", "Order", ["order_status", "pickup_date"])
    op.create_index("ix_order_student_status", "Order", ["student_id", "order_status"])

    # --- индексы ---
    op.create_index(op.f("ix_OrderDish_order_id"), "OrderDish", ["order_id"])
    op.create_index(op.f("ix_ScheduleDishes_date"), "ScheduleDishes", ["date"])
    op.create_index(op.f("ix_TemporaryCode_user_id"), "TemporaryCode", ["user_id"])
    op.create_index(op.f("ix_Users_institution_id"), "Users", ["institution_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_Users_institution_id"), table_name="Users")
    op.drop_index(op.f("ix_TemporaryCode_user_id"), table_name="TemporaryCode")
    op.drop_index(op.f("ix_ScheduleDishes_date"), table_name="ScheduleDishes")
    op.drop_index(op.f("ix_OrderDish_order_id"), table_name="OrderDish")
    op.drop_index("ix_order_student_status", table_name="Order")
    op.drop_index("ix_order_status_pickup_date", table_name="Order")
    op.drop_column("Order", "pickup_date")
    op.drop_constraint("uq_cart_schedule_dish", "ShoppingCartDishes", type_="unique")
    op.drop_constraint("uq_dish_institution_name", "Dishes", type_="unique")
    op.alter_column("Dishes", "is_active", existing_type=sa.Boolean(), nullable=True, server_default=None)
