"""Institution meal-set templates and their component dishes."""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "MealSet",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("institution_id", sa.Integer, sa.ForeignKey("EducationInstitution.id"), nullable=False),
        sa.Column("cycle_week", sa.Integer, nullable=False),
        sa.Column("weekday", sa.Integer, nullable=False),
        sa.Column("meal_type", sa.String, nullable=False),
        sa.Column("price", sa.Integer, nullable=False),
        sa.UniqueConstraint("institution_id", "cycle_week", "weekday", "meal_type", name="uq_meal_set_slot"),
        sa.CheckConstraint("cycle_week IN (1, 2)", name="ck_meal_set_week"),
        sa.CheckConstraint("weekday BETWEEN 0 AND 4", name="ck_meal_set_weekday"),
        sa.CheckConstraint("meal_type IN ('breakfast', 'lunch', 'afternoon_snack', 'dinner')", name="ck_meal_set_type"),
        sa.CheckConstraint("price > 0 AND price <= 100000", name="ck_meal_set_price"),
    )
    op.create_table(
        "MealSetComponent",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("meal_set_id", sa.Integer, sa.ForeignKey("MealSet.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dish_id", sa.Integer, sa.ForeignKey("Dishes.id"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.UniqueConstraint("meal_set_id", "dish_id", name="uq_meal_set_component"),
    )


def downgrade():
    op.drop_table("MealSetComponent")
    op.drop_table("MealSet")
