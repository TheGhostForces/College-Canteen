"""Domain integrity and immutable order-price snapshots.

Invalid legacy rows are deliberately not repaired; resolve the reported problem
explicitly before retrying. Historic prices before this revision are unknowable:
existing order lines are backfilled with their current catalog price.
"""

import sqlalchemy as sa

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

CHECKS = [
    ("Users", "ck_users_role", "role IN ('student', 'provider', 'operator', 'admin')"),
    ("Students", "ck_students_dates", "date_end >= date_start"),
    ("TemporaryCode", "ck_temporary_code_attempts", "attempts >= 0"),
    ("TemporaryCode", "ck_temporary_code_dates", "expires_at > created_at"),
    ("Dishes", "ck_dishes_price", "fixed_price > 0"),
    ("Dishes", "ck_dishes_category", "category IN ('Первое', 'Второе', 'Напитки', 'Десерт', 'Снеки')"),
    ("ScheduleDishes", "ck_schedule_quantities", "quantity >= 0 AND total_quantity >= quantity"),
    ("ShoppingCartDishes", "ck_cart_dishes_quantity", "cart_quantity > 0"),
    ("OrderDish", "ck_order_dishes_quantity", "cart_quantity > 0"),
]


def _fail_if_rows(sql: str, description: str) -> None:
    if op.get_bind().execute(sa.text(sql)).first() is not None:
        raise RuntimeError(
            f"Cannot apply migration 0003: invalid legacy data ({description}). "
            "No legacy rows are repaired/deleted; fix the data explicitly and retry. "
            f"Diagnostic query: {sql}"
        )


def upgrade() -> None:
    # Prevent writes between the preflight checks and constraint creation.
    # PostgreSQL's transactional DDL rolls everything back on any failure.
    op.execute(
        'LOCK TABLE "Users", "Students", "TemporaryCode", "Dishes", '
        '"ScheduleDishes", "ShoppingCart", "ShoppingCartDishes", "Order", "OrderDish" '
        "IN ACCESS EXCLUSIVE MODE"
    )
    for table, name, condition in CHECKS:
        _fail_if_rows(f'SELECT id FROM "{table}" WHERE NOT ({condition}) LIMIT 1', name)
    _fail_if_rows(
        'SELECT lower(email) FROM "Users" GROUP BY lower(email) HAVING count(*) > 1 LIMIT 1',
        "case-insensitive duplicate user email",
    )
    _fail_if_rows(
        'SELECT student_id FROM "ShoppingCart" GROUP BY student_id HAVING count(*) > 1 LIMIT 1',
        "multiple carts per student",
    )
    _fail_if_rows(
        "SELECT student_id FROM \"Order\" WHERE order_status = 'IN_PROGRESS' "
        "GROUP BY student_id HAVING count(*) > 1 LIMIT 1",
        "multiple active orders per student",
    )
    _fail_if_rows(
        'SELECT od.id FROM "OrderDish" od LEFT JOIN "Dishes" d ON d.id = od.dish_id '
        "WHERE d.id IS NULL OR d.fixed_price <= 0 LIMIT 1",
        "order line without valid catalog price for backfill",
    )

    op.add_column("OrderDish", sa.Column("unit_price", sa.Integer(), nullable=True))
    op.execute('UPDATE "OrderDish" od SET unit_price = d.fixed_price FROM "Dishes" d WHERE d.id = od.dish_id')
    op.alter_column("OrderDish", "unit_price", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint("ck_order_dishes_price", "OrderDish", "unit_price > 0")

    op.create_index("uq_users_email_lower", "Users", [sa.text("lower(email)")], unique=True)
    op.create_unique_constraint("uq_cart_student", "ShoppingCart", ["student_id"])
    op.create_index(
        "uq_order_student_active",
        "Order",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("order_status = 'IN_PROGRESS'"),
    )
    for table, name, condition in CHECKS:
        op.create_check_constraint(name, table, condition)


def downgrade() -> None:
    for table, name, _ in reversed(CHECKS):
        op.drop_constraint(name, table, type_="check")
    op.drop_index("uq_order_student_active", table_name="Order")
    op.drop_constraint("uq_cart_student", "ShoppingCart", type_="unique")
    op.drop_index("uq_users_email_lower", table_name="Users")
    op.drop_constraint("ck_order_dishes_price", "OrderDish", type_="check")
    op.drop_column("OrderDish", "unit_price")
