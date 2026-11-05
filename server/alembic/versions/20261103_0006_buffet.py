"""Persistent buffet offerings."""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    stock = connection.scalar(
        sa.text('SELECT EXISTS (SELECT 1 FROM "ScheduleDishes" WHERE total_quantity > 0 OR quantity > 0)')
    )
    active = connection.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM \"Order\" WHERE order_status = 'IN_PROGRESS')"))
    if stock or active:
        raise RuntimeError(
            "Cannot upgrade buffet schema with legacy scheduled stock or active legacy orders; "
            "reconcile stock and fulfill or cancel outstanding orders before retrying."
        )
    op.add_column("Order", sa.Column("institution_id", sa.Integer, sa.ForeignKey("EducationInstitution.id")))
    op.drop_index("uq_order_student_active", table_name="Order")
    op.create_table(
        "BuffetOffering",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dish_id", sa.Integer, sa.ForeignKey("Dishes.id"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("is_visible", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("dish_id", name="uq_buffet_dish"),
        sa.CheckConstraint("quantity >= 0", name="ck_buffet_quantity"),
    )
    op.create_table(
        "TypedCartItem",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("cart_id", sa.Integer, sa.ForeignKey("ShoppingCart.id", ondelete="CASCADE"), nullable=False),
        sa.Column("buffet_offering_id", sa.Integer, sa.ForeignKey("BuffetOffering.id")),
        sa.Column("meal_set_id", sa.Integer),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("pickup_date", sa.Date, nullable=False),
        sa.Column("unit_price", sa.Integer, nullable=False),
        sa.Column("material_snapshot", sa.JSON),
        sa.CheckConstraint("quantity > 0 AND unit_price > 0", name="ck_typed_cart_quantity"),
        sa.CheckConstraint(
            "(buffet_offering_id IS NOT NULL)::int + (meal_set_id IS NOT NULL)::int = 1", name="ck_typed_cart_kind"
        ),
        sa.UniqueConstraint("cart_id", "buffet_offering_id", name="uq_typed_cart_buffet"),
        sa.UniqueConstraint("cart_id", "meal_set_id", name="uq_typed_cart_set"),
    )
    op.create_table(
        "TypedOrderItem",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("Order.id"), nullable=False),
        sa.Column("buffet_offering_id", sa.Integer, sa.ForeignKey("BuffetOffering.id")),
        sa.Column("meal_set_id", sa.Integer),
        sa.Column("item_type", sa.String, nullable=False),
        sa.Column("meal_type", sa.String),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Integer, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.CheckConstraint("quantity > 0 AND unit_price > 0", name="ck_typed_order_values"),
    )
    op.create_index("ix_TypedOrderItem_order_id", "TypedOrderItem", ["order_id"])


def downgrade():
    connection = op.get_bind()
    for table in ("TypedOrderItem", "TypedCartItem", "BuffetOffering"):
        if connection.scalar(sa.text("SELECT to_regclass(:name)"), {"name": f'"{table}"'}):
            if connection.scalar(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{table}")')):
                raise RuntimeError(
                    "Cannot downgrade buffet schema without losing typed orders, carts or stock; "
                    "export and reconcile this data before retrying."
                )
    if connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM \"Order\" WHERE order_status = 'IN_PROGRESS' "
            "GROUP BY student_id HAVING count(*) > 1)"
        )
    ):
        raise RuntimeError("Cannot downgrade with multiple active orders per student; resolve them before retrying.")
    has_institution = connection.scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'Order' AND column_name = 'institution_id')"
        )
    )
    if has_institution and connection.scalar(
        sa.text('SELECT EXISTS (SELECT 1 FROM "Order" WHERE institution_id IS NOT NULL)')
    ):
        raise RuntimeError(
            "Cannot downgrade without losing order institution snapshots; export and reconcile them first."
        )
    op.execute('DROP TABLE IF EXISTS "TypedOrderItem"')
    op.execute('DROP TABLE IF EXISTS "TypedCartItem"')
    op.drop_table("BuffetOffering")
    op.execute('ALTER TABLE "Order" DROP COLUMN IF EXISTS institution_id')
    op.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_order_student_active ON "Order" (student_id) '
        "WHERE order_status = 'IN_PROGRESS'"
    )
