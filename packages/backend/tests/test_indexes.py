"""Tests to verify composite DB indexes are defined on all relevant models."""
import pytest
from sqlalchemy import create_engine, inspect
from app import models  # noqa: F401 — registers all models
from app.extensions import db


def _get_index_names(inspector, table_name):
    """Return a set of index names for a given table."""
    return {idx['name'] for idx in inspector.get_indexes(table_name)}


@pytest.fixture(scope="module")
def sqlite_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    db.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_expense_user_date_index(sqlite_engine):
    """ix_expense_user_date — most critical index for dashboard queries."""
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'expenses')
    assert 'ix_expense_user_date' in names, f"Missing ix_expense_user_date; found: {names}"


def test_expense_user_currency_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'expenses')
    assert 'ix_expense_user_currency' in names, f"Missing ix_expense_user_currency; found: {names}"


def test_expense_user_category_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'expenses')
    assert 'ix_expense_user_category' in names, f"Missing ix_expense_user_category; found: {names}"


def test_expense_user_type_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'expenses')
    assert 'ix_expense_user_type' in names, f"Missing ix_expense_user_type; found: {names}"


def test_expense_created_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'expenses')
    assert 'ix_expense_created' in names, f"Missing ix_expense_created; found: {names}"


def test_recurring_user_active_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'recurring_expenses')
    assert 'ix_recurring_user_active' in names, f"Missing ix_recurring_user_active; found: {names}"


def test_recurring_user_dates_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'recurring_expenses')
    assert 'ix_recurring_user_dates' in names, f"Missing ix_recurring_user_dates; found: {names}"


def test_bill_user_due_index(sqlite_engine):
    """ix_bill_user_due — critical for due-soon queries."""
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'bills')
    assert 'ix_bill_user_due' in names, f"Missing ix_bill_user_due; found: {names}"


def test_bill_user_active_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'bills')
    assert 'ix_bill_user_active' in names, f"Missing ix_bill_user_active; found: {names}"


def test_reminder_user_send_at_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'reminders')
    assert 'ix_reminder_user_send_at' in names, f"Missing ix_reminder_user_send_at; found: {names}"


def test_reminder_unsent_index(sqlite_engine):
    """ix_reminder_unsent — exact pattern used by scheduler to find pending reminders."""
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'reminders')
    assert 'ix_reminder_unsent' in names, f"Missing ix_reminder_unsent; found: {names}"


def test_category_user_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'categories')
    assert 'ix_category_user' in names, f"Missing ix_category_user; found: {names}"


def test_audit_user_created_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'audit_logs')
    assert 'ix_audit_user_created' in names, f"Missing ix_audit_user_created; found: {names}"


def test_ad_user_created_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'ad_impressions')
    assert 'ix_ad_user_created' in names, f"Missing ix_ad_user_created; found: {names}"


def test_subscription_user_active_index(sqlite_engine):
    inspector = inspect(sqlite_engine)
    names = _get_index_names(inspector, 'user_subscriptions')
    assert 'ix_subscription_user_active' in names, f"Missing ix_subscription_user_active; found: {names}"


def test_all_expense_indexes_columns(sqlite_engine):
    """Verify ix_expense_user_date covers the right columns (user_id, spent_at)."""
    inspector = inspect(sqlite_engine)
    indexes = {idx['name']: idx for idx in inspector.get_indexes('expenses')}
    idx = indexes.get('ix_expense_user_date', {})
    cols = idx.get('column_names', [])
    assert 'user_id' in cols and 'spent_at' in cols, \
        f"ix_expense_user_date should cover user_id+spent_at, got: {cols}"


def test_reminder_unsent_columns(sqlite_engine):
    """Verify ix_reminder_unsent covers user_id, sent, send_at."""
    inspector = inspect(sqlite_engine)
    indexes = {idx['name']: idx for idx in inspector.get_indexes('reminders')}
    idx = indexes.get('ix_reminder_unsent', {})
    cols = idx.get('column_names', [])
    assert 'user_id' in cols and 'sent' in cols and 'send_at' in cols, \
        f"ix_reminder_unsent should cover user_id+sent+send_at, got: {cols}"
