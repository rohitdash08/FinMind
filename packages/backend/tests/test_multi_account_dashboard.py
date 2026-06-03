"""
Tests for multi-account dashboard
"""
import pytest
from ..services.multi_account_dashboard import (
    get_user_accounts,
    get_dashboard_summary,
    format_currency,
    Account,
    DashboardSummary
)


def test_get_user_accounts():
    accounts = get_user_accounts("user_1")
    assert len(accounts) == 3
    assert all(isinstance(acc, Account) for acc in accounts)


def test_get_dashboard_summary():
    summary = get_dashboard_summary("user_1")
    assert isinstance(summary, DashboardSummary)
    assert summary.total_balance == 70000.00


def test_accounts_by_type():
    summary = get_dashboard_summary("user_1")
    assert "checking" in summary.by_type
    assert summary.by_type["checking"] == 5000.00


def test_format_currency():
    assert format_currency(1234.56) == "$1,234.56"
    assert format_currency(1000000) == "$1,000,000.00"
