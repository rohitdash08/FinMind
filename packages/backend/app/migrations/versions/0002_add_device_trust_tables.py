"""add device trust management tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-30 23:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("accept_language", sa.String(100), nullable=True),
        sa.Column("trust_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_devices_user_fingerprint", "devices", ["user_id", "fingerprint"])
    op.create_index("idx_devices_user_ip", "devices", ["user_id", "ip_address"])


def downgrade() -> None:
    op.drop_index("idx_devices_user_ip", table_name="devices")
    op.drop_index("idx_devices_user_fingerprint", table_name="devices")
    op.drop_table("devices")
