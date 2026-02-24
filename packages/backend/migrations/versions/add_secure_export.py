"""Add secure backup and encrypted export support

This migration is a schema-free stub.  The export feature does not
require any new database tables or columns — all data is read from
existing tables and streamed to the client at request time.

Revision ID: k1l2m3n4o5p6
Revises: j0k1l2m3n4o5
Create Date: 2026-02-24
"""
from alembic import op  # noqa: F401 (required by Alembic runner)

revision = "k1l2m3n4o5p6"
down_revision = "j0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade():
    """No schema changes required for the export feature."""
    pass


def downgrade():
    """No schema changes to revert."""
    pass
