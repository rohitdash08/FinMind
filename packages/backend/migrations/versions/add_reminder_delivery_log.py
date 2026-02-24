"""Add reminder_delivery_logs table for reliability tracking

Revision ID: f6a7b8c9d0e1
Revises: None
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e1"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "reminder_delivery_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "reminder_id",
            sa.Integer(),
            sa.ForeignKey("reminders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("attempted_at", sa.DateTime(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column("latency_seconds", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_delivery_log_reminder", "reminder_delivery_logs", ["reminder_id"]
    )
    op.create_index(
        "ix_delivery_log_attempted", "reminder_delivery_logs", ["attempted_at"]
    )
    op.create_index(
        "ix_delivery_log_success", "reminder_delivery_logs", ["success"]
    )


def downgrade():
    op.drop_index("ix_delivery_log_success", table_name="reminder_delivery_logs")
    op.drop_index("ix_delivery_log_attempted", table_name="reminder_delivery_logs")
    op.drop_index("ix_delivery_log_reminder", table_name="reminder_delivery_logs")
    op.drop_table("reminder_delivery_logs")
