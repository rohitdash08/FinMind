"""Add job_execution_logs and reminder_delivery_logs tables for background job monitoring

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reminder_delivery_logs',
        sa.Column('id',              sa.Integer(),   nullable=False),
        sa.Column('reminder_id',     sa.Integer(),   nullable=False),
        sa.Column('channel',         sa.String(20),  nullable=False),
        sa.Column('attempted_at',    sa.DateTime(),  nullable=False),
        sa.Column('success',         sa.Boolean(),   nullable=False, server_default='0'),
        sa.Column('error_message',   sa.String(500), nullable=True),
        sa.Column('latency_seconds', sa.Float(),     nullable=True),
        sa.ForeignKeyConstraint(['reminder_id'], ['reminders.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'job_execution_logs',
        sa.Column('id',                sa.Integer(),    nullable=False),
        sa.Column('job_name',          sa.String(100),  nullable=False),
        sa.Column('started_at',        sa.DateTime(),   nullable=False),
        sa.Column('finished_at',       sa.DateTime(),   nullable=True),
        sa.Column('status',            sa.String(20),   nullable=False, server_default='RUNNING'),
        sa.Column('records_processed', sa.Integer(),    nullable=False, server_default='0'),
        sa.Column('records_failed',    sa.Integer(),    nullable=False, server_default='0'),
        sa.Column('error_message',     sa.String(500),  nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_job_log_name',    'job_execution_logs', ['job_name'])
    op.create_index('ix_job_log_started', 'job_execution_logs', ['started_at'])


def downgrade():
    op.drop_index('ix_job_log_started', table_name='job_execution_logs')
    op.drop_index('ix_job_log_name',    table_name='job_execution_logs')
    op.drop_table('job_execution_logs')
    op.drop_table('reminder_delivery_logs')
