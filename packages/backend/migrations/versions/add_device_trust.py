"""Add trusted_devices table for device trust management

Revision ID: j0k1l2m3n4o5
Revises: i9j0k1l2m3n4
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'j0k1l2m3n4o5'
down_revision = 'i9j0k1l2m3n4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'trusted_devices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('device_fingerprint', sa.String(64), nullable=False),
        sa.Column('user_agent', sa.String(500), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('device_name', sa.String(100), nullable=True),
        sa.Column('trusted', sa.Boolean(), nullable=False, server_default=sa.text('0')),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'device_fingerprint', name='uq_device_user_fp'),
    )
    op.create_index('ix_device_user', 'trusted_devices', ['user_id'])
    op.create_index('ix_device_trusted', 'trusted_devices', ['user_id', 'trusted'])


def downgrade():
    op.drop_index('ix_device_trusted', table_name='trusted_devices')
    op.drop_index('ix_device_user', table_name='trusted_devices')
    op.drop_table('trusted_devices')
