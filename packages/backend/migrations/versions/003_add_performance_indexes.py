"""Add database indexes for high-frequency financial queries

Revision ID: 003_perf_indexes
Revises: 002
Create Date: 2026-04-05
"""
from alembic import op

revision = "003_perf_indexes"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # expenses: user_id + spent_at — most common dashboard query
    op.create_index("ix_expenses_user_spent", "expenses", ["user_id", "spent_at"])
    # expenses: user_id + category_id — category breakdown queries
    op.create_index("ix_expenses_user_category", "expenses", ["user_id", "category_id"])
    # expenses: user_id + expense_type — income vs expense splits
    op.create_index("ix_expenses_user_type", "expenses", ["user_id", "expense_type"])
    # recurring_expenses: user_id + active — active recurring fetch
    op.create_index("ix_recurring_user_active", "recurring_expenses", ["user_id", "active"])
    # bills: user_id + due_date — upcoming bills queries
    op.create_index("ix_bills_user_due", "bills", ["user_id", "due_date"])
    # categories: user_id — all category lookups are by user
    op.create_index("ix_categories_user", "categories", ["user_id"])


def downgrade():
    op.drop_index("ix_expenses_user_spent", "expenses")
    op.drop_index("ix_expenses_user_category", "expenses")
    op.drop_index("ix_expenses_user_type", "expenses")
    op.drop_index("ix_recurring_user_active", "recurring_expenses")
    op.drop_index("ix_bills_user_due", "bills")
    op.drop_index("ix_categories_user", "categories")
