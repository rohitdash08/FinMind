"""Add category_budgets table for overspend early warning

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'category_budgets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('category_id', sa.Integer(), sa.ForeignKey('categories.id'), nullable=False),
        sa.Column('monthly_limit', sa.Numeric(12, 2), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='INR'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'category_id', name='uq_budget_user_category'),
    )
    op.create_index('ix_budget_user', 'category_budgets', ['user_id'])


def downgrade():
    op.drop_index('ix_budget_user', table_name='category_budgets')
    op.drop_table('category_budgets')
