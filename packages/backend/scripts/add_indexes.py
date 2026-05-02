"""Add performance indexes to FinMind database.

Run this script against an existing PostgreSQL database to create the
indexes introduced in GitHub issue #128.  The statements are idempotent
(CREATE INDEX IF NOT EXISTS) so they can be re-run safely.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.extensions import db


INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_expenses_user_spent_at ON expenses (user_id, spent_at)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_user_category ON expenses (user_id, category_id)",
    "CREATE INDEX IF NOT EXISTS ix_expenses_user_type_spent ON expenses (user_id, expense_type, spent_at)",
    "CREATE INDEX IF NOT EXISTS ix_bills_user_due ON bills (user_id, next_due_date)",
    "CREATE INDEX IF NOT EXISTS ix_bills_user_active ON bills (user_id, active)",
    "CREATE INDEX IF NOT EXISTS ix_reminders_user_send_at ON reminders (user_id, send_at)",
    "CREATE INDEX IF NOT EXISTS ix_reminders_pending ON reminders (user_id, sent, send_at)",
    "CREATE INDEX IF NOT EXISTS ix_categories_user ON categories (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_recurring_user_active ON recurring_expenses (user_id, active)",
    "CREATE INDEX IF NOT EXISTS ix_bg_jobs_status_retry ON background_jobs (status, next_retry_at)",
    "CREATE INDEX IF NOT EXISTS ix_bg_jobs_type ON background_jobs (job_type)",
]


def add_indexes():
    app = create_app()
    with app.app_context():
        conn = db.engine.raw_connection()
        try:
            cur = conn.cursor()
            for idx_sql in INDEXES:
                print(f"Creating: {idx_sql}")
                cur.execute(idx_sql)
            conn.commit()
            print("All indexes created successfully.")
        finally:
            conn.close()


if __name__ == "__main__":
    add_indexes()
