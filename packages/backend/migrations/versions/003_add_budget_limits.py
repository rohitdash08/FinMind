"""add budget_limits table

Revision ID: 003
Revises: 002
Create Date: 2026-04-04
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "budget_limits",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("monthly_limit", sa.Numeric(12, 2), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "category_id", "month", name="uq_budget_user_cat_month"),
    )


def downgrade():
    op.drop_table("budget_limits")
