"""create payee merchant alias table

Revision ID: xxxx
Revises: <previous_revision_id>
Create Date: 2024-01-01 12:00:00.000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'xxxx'
down_revision = '<previous_revision_id>' # Placeholder: replace with actual previous revision ID
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payee_merchant_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("raw_name", sa.String(length=255), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", sa.func.lower(sa.column("raw_name")), name="uq_user_raw_name")
    )


def downgrade():
    op.drop_table("payee_merchant_aliases")

