"""add database indexes for financial queries

Revision ID: 0001
Revises:
Create Date: 2026-05-30 23:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("idx_expenses_user_spent_at", "expenses", ["user_id", sa.text("spent_at DESC")], postgresql_using="btree")
    op.create_index("idx_categories_user_id", "categories", ["user_id"], postgresql_using="btree")
    op.create_index("idx_bills_user_due", "bills", ["user_id", "next_due_date"], postgresql_using="btree")
    op.create_index("idx_reminders_user_created", "reminders", ["user_id", "created_at"], postgresql_using="btree")


def downgrade() -> None:
    op.drop_index("idx_expenses_user_spent_at", table_name="expenses")
    op.drop_index("idx_categories_user_id", table_name="categories")
    op.drop_index("idx_bills_user_due", table_name="bills")
    op.drop_index("idx_reminders_user_created", table_name="reminders")
