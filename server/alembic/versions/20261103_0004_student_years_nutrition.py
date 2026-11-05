"""Replace student dates with study years and add serving nutrition.

The previous database is expected to be empty; no historical conversion is made.
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

NUTRITION = ("serving_weight_g", "energy_kcal", "protein_g", "fat_g", "carbohydrates_g")


def _require_empty_students():
    if op.get_bind().execute(sa.text('SELECT 1 FROM "Students" LIMIT 1')).first():
        raise RuntimeError("Students must be empty when changing study year columns")


def upgrade():
    _require_empty_students()
    op.add_column("EducationInstitution", sa.Column("cycle_start_monday", sa.Date(), nullable=True))
    op.create_check_constraint("ck_institution_cycle_monday", "EducationInstitution", "EXTRACT(ISODOW FROM cycle_start_monday) = 1")
    op.drop_constraint("ck_students_dates", "Students", type_="check")
    op.drop_column("Students", "date_start")
    op.drop_column("Students", "date_end")
    op.add_column("Students", sa.Column("study_start_year", sa.Integer(), nullable=False))
    op.add_column("Students", sa.Column("study_end_year", sa.Integer(), nullable=False))
    op.create_check_constraint("ck_students_years", "Students", "study_end_year >= study_start_year")
    op.drop_constraint("ck_dishes_category", "Dishes", type_="check")
    op.create_check_constraint("ck_dishes_category", "Dishes", "length(trim(category)) > 0")
    for name in NUTRITION:
        op.add_column("Dishes", sa.Column(name, sa.Float(), server_default=sa.text("0"), nullable=False))
    op.create_check_constraint("ck_dishes_nutrition", "Dishes", " AND ".join(f"{name} >= 0" for name in NUTRITION))


def downgrade():
    _require_empty_students()
    op.drop_constraint("ck_institution_cycle_monday", "EducationInstitution", type_="check")
    op.drop_column("EducationInstitution", "cycle_start_monday")
    op.drop_constraint("ck_dishes_nutrition", "Dishes", type_="check")
    for name in reversed(NUTRITION):
        op.drop_column("Dishes", name)
    op.drop_constraint("ck_dishes_category", "Dishes", type_="check")
    op.create_check_constraint("ck_dishes_category", "Dishes", "category IN ('Первое', 'Второе', 'Напитки', 'Десерт', 'Снеки')")
    op.drop_constraint("ck_students_years", "Students", type_="check")
    op.drop_column("Students", "study_end_year")
    op.drop_column("Students", "study_start_year")
    op.add_column("Students", sa.Column("date_start", sa.Date(), nullable=False))
    op.add_column("Students", sa.Column("date_end", sa.Date(), nullable=False))
    op.create_check_constraint("ck_students_dates", "Students", "date_end >= date_start")
