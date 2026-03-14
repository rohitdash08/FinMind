"""
Database index report utility (Issue #128).

Run with: flask index-report

Reports: current indexes, missing recommended indexes, table sizes.
Helps track index health in production.
"""

from __future__ import annotations

import click
from flask import Flask
from flask.cli import with_appcontext

from ..extensions import db

# Expected indexes — checked at startup in dev/test to catch regressions
REQUIRED_INDEXES = [
    "idx_expenses_user_spent_at",
    "idx_expenses_user_category",
    "idx_expenses_user_type_date",
    "idx_expenses_user_month",
    "idx_bills_user_due",
    "idx_bills_user_active_due",
    "idx_reminders_due",
    "idx_reminders_pending_dispatch",
    "idx_recurring_expenses_user_start",
    "idx_recurring_expenses_active",
    "idx_categories_user_name",
    "idx_audit_logs_user_created",
    "idx_audit_logs_action_created",
]


def get_existing_indexes(engine) -> list[str]:
    """Query pg_indexes for all FinMind indexes."""
    if engine.dialect.name != "postgresql":
        return []
    with engine.connect() as conn:
        result = conn.execute(
            db.text(
                """
                SELECT indexname FROM pg_indexes
                WHERE schemaname = 'public'
                ORDER BY indexname
                """
            )
        )
        return [row[0] for row in result]


def check_missing_indexes(engine) -> list[str]:
    """Return list of recommended indexes not yet present."""
    existing = set(get_existing_indexes(engine))
    return [idx for idx in REQUIRED_INDEXES if idx not in existing]


def register_index_cli(app: Flask) -> None:
    """Register the flask index-report CLI command."""

    @app.cli.command("index-report")
    @with_appcontext
    def index_report():
        """Print a report of database indexes and missing recommendations."""
        engine = db.engine
        if engine.dialect.name != "postgresql":
            click.echo("Index report only supported on PostgreSQL.")
            return

        existing = get_existing_indexes(engine)
        missing = check_missing_indexes(engine)

        click.echo(f"\n{'='*60}")
        click.echo("FinMind Database Index Report")
        click.echo(f"{'='*60}")
        click.echo(f"\nTotal indexes: {len(existing)}")
        for idx in sorted(existing):
            status = "✅" if idx in REQUIRED_INDEXES else "  "
            click.echo(f"  {status} {idx}")

        if missing:
            click.echo(f"\n⚠️  Missing recommended indexes ({len(missing)}):")
            for idx in missing:
                click.echo(f"  ❌ {idx}")
            click.echo(
                "\nRun migration 007_db_indexing.sql to add missing indexes."
            )
        else:
            click.echo("\n✅ All recommended indexes are present.")
        click.echo(f"{'='*60}\n")
