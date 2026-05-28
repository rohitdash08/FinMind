"""
Tests for multi-account financial overview.
"""

import pytest
from app.services.accounts import (
    create_account,
    get_user_accounts,
    get_account_summary,
    transfer_between_accounts,
)


class TestAccountCreation:
    def test_create_checking(self, app, db_session):
        with app.app_context():
            acc = create_account(1, "Main Checking", "checking", balance=1000)
            assert acc.name == "Main Checking"
            assert acc.balance == 1000
            assert acc.account_type == "checking"

    def test_create_savings(self, app, db_session):
        with app.app_context():
            acc = create_account(1, "Savings", "savings", balance=5000, interest_rate=0.045)
            assert acc.interest_rate == 0.045

    def test_invalid_type(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                create_account(1, "Bad", "crypto_wallet")


class TestAccountSummary:
    def test_summary_empty(self, app, db_session):
        with app.app_context():
            summary = get_account_summary(999)
            assert summary["account_count"] == 0
            assert summary["total_balance"] == 0

    def test_summary_with_accounts(self, app, db_session):
        with app.app_context():
            create_account(1, "Checking", "checking", balance=2000)
            create_account(1, "Savings", "savings", balance=8000)
            create_account(1, "Credit Card", "credit_card", balance=-500)

            summary = get_account_summary(1)
            assert summary["account_count"] == 3
            assert summary["total_balance"] == 9500
            assert summary["assets"] > 0
            assert summary["liabilities"] == 500


class TestTransfers:
    def test_transfer_success(self, app, db_session):
        with app.app_context():
            a1 = create_account(1, "From", "checking", balance=1000)
            a2 = create_account(1, "To", "savings", balance=0)

            t = transfer_between_accounts(1, a1.id, a2.id, 500, "Test transfer")
            assert t.amount == 500

    def test_transfer_invalid_amount(self, app, db_session):
        with app.app_context():
            with pytest.raises(ValueError):
                transfer_between_accounts(1, 1, 2, -100)

    def test_transfer_same_account(self, app, db_session):
        with app.app_context():
            acc = create_account(1, "Test", "checking", balance=1000)
            with pytest.raises(ValueError):
                transfer_between_accounts(1, acc.id, acc.id, 100)
