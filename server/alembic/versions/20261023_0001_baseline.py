"""Исходная схема БД (состояние до появления Alembic).

Если база была создана раньше через metadata.create_all(), таблицы уже есть: миграция
ничего не делает, и дальше применяются только следующие ревизии. Пустая база создаётся целиком.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("Users"):
        return
    op.create_table('EducationInstitution',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('Dishes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('dish_name', sa.String(), nullable=False),
    sa.Column('category', sa.String(), nullable=False),
    sa.Column('fixed_price', sa.Integer(), nullable=False),
    sa.Column('img_url', sa.String(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.Column('institution_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['institution_id'], ['EducationInstitution.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('Users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('role', sa.String(), nullable=False),
    sa.Column('institution_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['institution_id'], ['EducationInstitution.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )
    op.create_table('ScheduleDishes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.Column('total_quantity', sa.Integer(), nullable=False),
    sa.Column('dish_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['dish_id'], ['Dishes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('dish_id', 'date', name='uq_dish_date')
    )
    op.create_table('Students',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('full_name', sa.String(), nullable=False),
    sa.Column('group_name', sa.String(), nullable=False),
    sa.Column('date_start', sa.Date(), nullable=False),
    sa.Column('date_end', sa.Date(), nullable=False),
    sa.Column('rating', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('TemporaryCode',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code_hash', sa.String(), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used_at', sa.DateTime(), nullable=True),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['Users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('Order',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('order_number', sa.String(), nullable=False),
    sa.Column('order_status', sa.Enum('IN_PROGRESS', 'CANCELLED', 'COMPLETED', 'EXPIRED', name='orderstatus'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['Students.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_Order_order_number'), 'Order', ['order_number'], unique=True)
    op.create_table('ShoppingCart',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('student_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['student_id'], ['Students.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('OrderDish',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cart_quantity', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('dish_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['dish_id'], ['Dishes.id'], ),
    sa.ForeignKeyConstraint(['order_id'], ['Order.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('ShoppingCartDishes',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('cart_quantity', sa.Integer(), nullable=False),
    sa.Column('shoppingcart_id', sa.Integer(), nullable=False),
    sa.Column('schedule_dish_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['schedule_dish_id'], ['ScheduleDishes.id'], ),
    sa.ForeignKeyConstraint(['shoppingcart_id'], ['ShoppingCart.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('ShoppingCartDishes')
    op.drop_table('OrderDish')
    op.drop_table('ShoppingCart')
    op.drop_index(op.f('ix_Order_order_number'), table_name='Order')
    op.drop_table('Order')
    op.drop_table('TemporaryCode')
    op.drop_table('Students')
    op.drop_table('ScheduleDishes')
    op.drop_table('Users')
    op.drop_table('Dishes')
    op.drop_table('EducationInstitution')
    op.execute("DROP TYPE IF EXISTS orderstatus")
