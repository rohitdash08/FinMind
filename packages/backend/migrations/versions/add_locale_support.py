"""Add locale formatting support: preferred_locale column + locale service

Revision ID: b2c3d4e5f6a7
Revises: None
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'b2c3d4e5f6a7'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users',
        sa.Column('preferred_locale', sa.String(20), nullable=False,
                  server_default='en_IN'))


def downgrade():
    op.drop_column('users', 'preferred_locale')
