"""Add priority and notification_type columns to reminders

Revision ID: g7h8i9j0k1l2
Revises: None
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'g7h8i9j0k1l2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('reminders', sa.Column('priority',          sa.String(10), nullable=False, server_default='NORMAL'))
    op.add_column('reminders', sa.Column('notification_type', sa.String(20), nullable=False, server_default='CUSTOM'))
    op.create_index('ix_reminder_priority', 'reminders', ['user_id', 'priority'])
    op.create_index('ix_reminder_type',     'reminders', ['user_id', 'notification_type'])
    op.create_index('ix_reminder_pending',  'reminders', ['user_id', 'sent', 'send_at'])


def downgrade():
    op.drop_index('ix_reminder_pending',  table_name='reminders')
    op.drop_index('ix_reminder_type',     table_name='reminders')
    op.drop_index('ix_reminder_priority', table_name='reminders')
    op.drop_column('reminders', 'notification_type')
    op.drop_column('reminders', 'priority')
