"""Add reminder delivery tracking

Revision ID: add_reminder_delivery_tracking
Revises: 
Create Date: 2026-03-29

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic
revision = 'add_reminder_delivery_tracking'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to reminders table
    op.add_column('reminders', sa.Column('delivered', sa.Boolean(), nullable=True))
    op.add_column('reminders', sa.Column('delivery_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('reminders', sa.Column('last_attempt_at', sa.DateTime(), nullable=True))
    op.add_column('reminders', sa.Column('error_message', sa.String(500), nullable=True))
    op.add_column('reminders', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()))
    
    # Create reminder_deliveries table
    op.create_table(
        'reminder_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('reminder_id', sa.Integer(), sa.ForeignKey('reminders.id'), nullable=False),
        sa.Column('attempted_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('error_message', sa.String(500), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
    )
    
    # Create index for faster queries
    op.create_index('ix_reminder_deliveries_reminder_id', 'reminder_deliveries', ['reminder_id'])
    op.create_index('ix_reminder_deliveries_attempted_at', 'reminder_deliveries', ['attempted_at'])


def downgrade():
    # Drop reminder_deliveries table
    op.drop_index('ix_reminder_deliveries_attempted_at', table_name='reminder_deliveries')
    op.drop_index('ix_reminder_deliveries_reminder_id', table_name='reminder_deliveries')
    op.drop_table('reminder_deliveries')
    
    # Drop columns from reminders table
    op.drop_column('reminders', 'created_at')
    op.drop_column('reminders', 'error_message')
    op.drop_column('reminders', 'last_attempt_at')
    op.drop_column('reminders', 'delivery_attempts')
    op.drop_column('reminders', 'delivered')
