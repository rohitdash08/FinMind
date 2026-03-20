"""Tests to verify database indexes exist on all expected tables/columns.

These tests inspect SQLAlchemy model metadata to ensure that the indexing
optimizations from issue #128 are correctly declared.
"""

from sqlalchemy import inspect as sa_inspect

from app.models import (
    AdImpression,
    AuditLog,
    Bill,
    Category,
    Expense,
    Reminder,
    RecurringExpense,
    User,
    UserSubscription,
)


def _index_names(model):
    """Return a set of index names declared on a model's table."""
    return {idx.name for idx in model.__table__.indexes}


def _index_columns(model):
    """Return a dict mapping index name -> tuple of column names."""
    return {
        idx.name: tuple(col.name for col in idx.columns)
        for idx in model.__table__.indexes
    }


# ------------------------------------------------------------------
# User
# ------------------------------------------------------------------

def test_user_created_at_index():
    assert "ix_users_created_at" in _index_names(User)
    assert _index_columns(User)["ix_users_created_at"] == ("created_at",)


# ------------------------------------------------------------------
# Category
# ------------------------------------------------------------------

def test_category_user_id_index():
    cols = {col.name for col in Category.__table__.columns}
    assert "user_id" in cols
    # user_id should be indexed (single-column)
    idx_cols = _index_columns(Category)
    has_user_id_idx = any(
        c[0] == "user_id" for c in idx_cols.values()
    )
    assert has_user_id_idx


def test_category_user_id_name_composite_index():
    idx = _index_columns(Category)
    assert "ix_categories_user_id_name" in idx
    assert idx["ix_categories_user_id_name"] == ("user_id", "name")


# ------------------------------------------------------------------
# Expense
# ------------------------------------------------------------------

def test_expense_single_column_indexes():
    names = _index_names(Expense)
    # At minimum user_id, category_id, spent_at should have column-level indexes
    idx = _index_columns(Expense)
    user_id_indexed = any("user_id" in cols for cols in idx.values())
    category_id_indexed = any("category_id" in cols for cols in idx.values())
    spent_at_indexed = any("spent_at" in cols for cols in idx.values())
    assert user_id_indexed, "user_id must be indexed"
    assert category_id_indexed, "category_id must be indexed"
    assert spent_at_indexed, "spent_at must be indexed"


def test_expense_user_id_spent_at_composite():
    idx = _index_columns(Expense)
    assert "ix_expenses_user_id_spent_at" in idx
    assert idx["ix_expenses_user_id_spent_at"] == ("user_id", "spent_at")


def test_expense_user_id_category_id_composite():
    idx = _index_columns(Expense)
    assert "ix_expenses_user_id_category_id" in idx
    assert idx["ix_expenses_user_id_category_id"] == ("user_id", "category_id")


def test_expense_user_id_type_spent_at_composite():
    idx = _index_columns(Expense)
    assert "ix_expenses_user_id_type_spent_at" in idx
    assert idx["ix_expenses_user_id_type_spent_at"] == (
        "user_id",
        "expense_type",
        "spent_at",
    )


def test_expense_user_id_recurring_spent_at_composite():
    idx = _index_columns(Expense)
    assert "ix_expenses_user_id_recurring_spent_at" in idx
    assert idx["ix_expenses_user_id_recurring_spent_at"] == (
        "user_id",
        "source_recurring_id",
        "spent_at",
    )


# ------------------------------------------------------------------
# RecurringExpense
# ------------------------------------------------------------------

def test_recurring_expense_user_id_active_composite():
    idx = _index_columns(RecurringExpense)
    assert "ix_recurring_expenses_user_id_active" in idx
    assert idx["ix_recurring_expenses_user_id_active"] == ("user_id", "active")


# ------------------------------------------------------------------
# Bill
# ------------------------------------------------------------------

def test_bill_user_id_active_due_composite():
    idx = _index_columns(Bill)
    assert "ix_bills_user_id_active_due" in idx
    assert idx["ix_bills_user_id_active_due"] == (
        "user_id",
        "active",
        "next_due_date",
    )


# ------------------------------------------------------------------
# Reminder
# ------------------------------------------------------------------

def test_reminder_user_id_sent_send_at_composite():
    idx = _index_columns(Reminder)
    assert "ix_reminders_user_id_sent_send_at" in idx
    assert idx["ix_reminders_user_id_sent_send_at"] == (
        "user_id",
        "sent",
        "send_at",
    )


def test_reminder_dedup_composite():
    idx = _index_columns(Reminder)
    assert "ix_reminders_user_id_bill_id_channel_send_at" in idx
    assert idx["ix_reminders_user_id_bill_id_channel_send_at"] == (
        "user_id",
        "bill_id",
        "channel",
        "send_at",
    )


# ------------------------------------------------------------------
# AdImpression
# ------------------------------------------------------------------

def test_ad_impression_created_at_index():
    assert "ix_ad_impressions_created_at" in _index_names(AdImpression)


# ------------------------------------------------------------------
# UserSubscription
# ------------------------------------------------------------------

def test_user_subscription_user_id_index():
    idx = _index_columns(UserSubscription)
    has_user_id = any("user_id" in cols for cols in idx.values())
    assert has_user_id


# ------------------------------------------------------------------
# AuditLog
# ------------------------------------------------------------------

def test_audit_log_user_id_created_at_composite():
    idx = _index_columns(AuditLog)
    assert "ix_audit_logs_user_id_created_at" in idx
    assert idx["ix_audit_logs_user_id_created_at"] == ("user_id", "created_at")


# ------------------------------------------------------------------
# Integration: indexes are actually created in SQLite
# ------------------------------------------------------------------

def test_indexes_created_in_database(app_fixture):
    """Verify that indexes are physically present after create_all."""
    with app_fixture.app_context():
        from app.extensions import db

        engine = db.engine
        inspector = sa_inspect(engine)

        # Check expenses table indexes
        expense_indexes = {idx["name"] for idx in inspector.get_indexes("expenses")}
        assert "ix_expenses_user_id_spent_at" in expense_indexes
        assert "ix_expenses_user_id_category_id" in expense_indexes
        assert "ix_expenses_user_id_type_spent_at" in expense_indexes

        # Check bills table indexes
        bill_indexes = {idx["name"] for idx in inspector.get_indexes("bills")}
        assert "ix_bills_user_id_active_due" in bill_indexes

        # Check reminders table indexes
        reminder_indexes = {
            idx["name"] for idx in inspector.get_indexes("reminders")
        }
        assert "ix_reminders_user_id_sent_send_at" in reminder_indexes
