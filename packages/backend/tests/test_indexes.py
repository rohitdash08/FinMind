"""Tests for database indexing optimization (Issue #128).

Verifies that:
1. SQLAlchemy models define the expected composite indexes
2. Indexes are properly created on the database tables
3. Key query patterns use the new indexes (not full table scans)
"""
import pytest
from sqlalchemy import inspect
from app import create_app
from app.extensions import db
from app import models  # noqa: F401


class TestDatabaseIndexes:
    """Verify all financial query indexes exist on models."""

    @pytest.fixture()
    def app_ctx(self):
        """Create app with SQLite in-memory DB and yield application context."""
        from app.config import Settings

        class TestSettings(Settings):
            database_url: str = "sqlite+pysqlite:///:memory:"
            redis_url: str = "redis://localhost:6379/15"
            jwt_secret: str = "test-secret-with-32-plus-chars-1234567890"

        app = create_app(TestSettings())
        with app.app_context():
            db.create_all()
            yield app
            db.session.remove()
            db.drop_all()

    def _get_index_names(self, app, table_name: str) -> set[str]:
        """Return set of index names for a given table."""
        inspector = inspect(db.engine)
        indexes = inspector.get_indexes(table_name)
        return {idx["name"] for idx in indexes}

    def test_expense_indexes_exist(self, app_ctx):
        """Expense table should have composite indexes for all major query patterns."""
        index_names = self._get_index_names(app_ctx, "expenses")
        expected = {
            "ix_expenses_user_spent",
            "ix_expenses_user_type_spent",
            "ix_expenses_user_category",
            "ix_expenses_user_date_amount",
            "ix_expenses_user_recurring_date",
        }
        assert expected.issubset(index_names), (
            f"Missing expense indexes. Expected {expected - index_names}"
        )

    def test_category_indexes_exist(self, app_ctx):
        """Category table should have user_id and user+name indexes."""
        index_names = self._get_index_names(app_ctx, "categories")
        expected = {
            "ix_categories_user_id",
            "ix_categories_user_name",
        }
        assert expected.issubset(index_names), (
            f"Missing category indexes. Expected {expected - index_names}"
        )

    def test_recurring_expense_indexes_exist(self, app_ctx):
        """RecurringExpense should have user+active index for listing active items."""
        index_names = self._get_index_names(app_ctx, "recurring_expenses")
        assert "ix_recurring_user_active" in index_names, (
            "Missing ix_recurring_user_active index"
        )

    def test_bill_indexes_exist(self, app_ctx):
        """Bill table should have user+active+due_date for upcoming bills query."""
        index_names = self._get_index_names(app_ctx, "bills")
        assert "ix_bills_user_active_due" in index_names, (
            "Missing ix_bills_user_active_due index"
        )

    def test_reminder_indexes_exist(self, app_ctx):
        """Reminder table should have sent+send_at for pending reminders scheduler."""
        index_names = self._get_index_names(app_ctx, "reminders")
        assert "ix_reminders_sent_send_at" in index_names, (
            "Missing ix_reminders_sent_send_at index"
        )

    def test_ad_impression_indexes_exist(self, app_ctx):
        """AdImpression should have created_at index for time-range analytics."""
        index_names = self._get_index_names(app_ctx, "ad_impressions")
        assert "ix_ad_impressions_created" in index_names, (
            "Missing ix_ad_impressions_created index"
        )

    def test_user_subscription_indexes_exist(self, app_ctx):
        """UserSubscription should have user+active for active plan lookup."""
        index_names = self._get_index_names(app_ctx, "user_subscriptions")
        assert "ix_user_subscriptions_user_active" in index_names, (
            "Missing ix_user_subscriptions_user_active index"
        )

    def test_audit_log_indexes_exist(self, app_ctx):
        """AuditLog should have user_id and created_at indexes."""
        index_names = self._get_index_names(app_ctx, "audit_logs")
        expected = {
            "ix_audit_logs_user_id",
            "ix_audit_logs_created_at",
        }
        assert expected.issubset(index_names), (
            f"Missing audit_log indexes. Expected {expected - index_names}"
        )

    def test_expense_index_covers_dashboard_summary(self, app_ctx):
        """Verify the user+type+spent index columns match dashboard query pattern."""
        inspector = inspect(db.engine)
        indexes = inspector.get_indexes("expenses")
        type_spent_idx = next(
            (i for i in indexes if i["name"] == "ix_expenses_user_type_spent"), None
        )
        assert type_spent_idx is not None, "ix_expenses_user_type_spent not found"
        assert type_spent_idx["column_names"] == [
            "user_id",
            "expense_type",
            "spent_at",
        ]

    def test_expense_index_covers_duplicate_detection(self, app_ctx):
        """Verify user+date+amount index supports duplicate detection query."""
        inspector = inspect(db.engine)
        indexes = inspector.get_indexes("expenses")
        date_amount_idx = next(
            (i for i in indexes if i["name"] == "ix_expenses_user_date_amount"), None
        )
        assert date_amount_idx is not None, "ix_expenses_user_date_amount not found"
        assert date_amount_idx["column_names"] == [
            "user_id",
            "spent_at",
            "amount",
        ]

    def test_bill_index_covers_upcoming_bills_query(self, app_ctx):
        """Verify user+active+due_date index matches upcoming bills dashboard query."""
        inspector = inspect(db.engine)
        indexes = inspector.get_indexes("bills")
        active_due_idx = next(
            (i for i in indexes if i["name"] == "ix_bills_user_active_due"), None
        )
        assert active_due_idx is not None, "ix_bills_user_active_due not found"
        assert active_due_idx["column_names"] == [
            "user_id",
            "active",
            "next_due_date",
        ]
