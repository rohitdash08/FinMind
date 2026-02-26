"""Tests for data models."""

import pytest
from datetime import datetime
from models.transaction import (
    Account, AccountType, Balance, Currency, Transaction,
    TransactionStatus, TransactionType,
)
from models.sync_state import SyncState, SyncStatus


class TestAccount:
    def test_create_account(self):
        acct = Account(account_id="a1", name="Checking", account_type=AccountType.CHECKING)
        assert acct.account_id == "a1"
        assert acct.name == "Checking"
        assert acct.currency == Currency.USD

    def test_auto_id(self):
        acct = Account(account_id="", name="Test", account_type=AccountType.SAVINGS)
        assert len(acct.account_id) > 0  # UUID generated


class TestTransaction:
    def test_create_transaction(self):
        txn = Transaction(
            transaction_id="t1", account_id="a1", amount=-50.0,
            date=datetime(2025, 1, 15), description="Coffee Shop",
        )
        assert txn.transaction_id == "t1"
        assert txn.is_debit is True
        assert txn.is_credit is False

    def test_credit_transaction(self):
        txn = Transaction(
            transaction_id="t2", account_id="a1", amount=1000.0,
            date=datetime(2025, 1, 15), description="Payroll",
        )
        assert txn.is_credit is True
        assert txn.is_debit is False

    def test_auto_id(self):
        txn = Transaction(
            transaction_id="", account_id="a1", amount=10.0,
            date=datetime(2025, 1, 1), description="Test",
        )
        assert len(txn.transaction_id) > 0


class TestBalance:
    def test_basic_balance(self):
        bal = Balance(account_id="a1", current=5000.0, available=4950.0)
        assert bal.current == 5000.0
        assert bal.utilization is None

    def test_credit_utilization(self):
        bal = Balance(account_id="a1", current=-2500.0, limit=5000.0)
        assert bal.utilization == 0.5

    def test_zero_limit(self):
        bal = Balance(account_id="a1", current=100.0, limit=0.0)
        assert bal.utilization is None


class TestSyncState:
    def test_initial_state(self):
        state = SyncState(connector_id="c1")
        assert state.status == SyncStatus.IDLE
        assert state.is_healthy is True
        assert state.needs_sync is True

    def test_mark_started(self):
        state = SyncState(connector_id="c1")
        state.mark_started()
        assert state.status == SyncStatus.SYNCING

    def test_mark_success(self):
        state = SyncState(connector_id="c1")
        state.mark_started()
        state.mark_success(synced_count=10, cursor="abc")
        assert state.status == SyncStatus.SUCCESS
        assert state.total_synced == 10
        assert state.cursor == "abc"
        assert state.last_success_at is not None
        assert state.needs_sync is False

    def test_mark_failed(self):
        state = SyncState(connector_id="c1")
        state.mark_failed("timeout")
        assert state.status == SyncStatus.FAILED
        assert state.error_count == 1
        assert state.error_message == "timeout"

    def test_unhealthy_after_failures(self):
        state = SyncState(connector_id="c1")
        state.mark_failed("err1")
        # status=FAILED means unhealthy regardless of count
        assert state.is_healthy is False
        state.mark_failed("err2")
        assert state.is_healthy is False
        state.mark_failed("err3")
        assert state.is_healthy is False
        assert state.error_count == 3

    def test_success_resets_error_count(self):
        state = SyncState(connector_id="c1")
        state.mark_failed("err1")
        state.mark_failed("err2")
        state.mark_success(synced_count=5)
        assert state.error_count == 0
        assert state.is_healthy is True

    def test_mark_partial(self):
        state = SyncState(connector_id="c1")
        state.mark_partial(synced_count=3, error="partial fail")
        assert state.status == SyncStatus.PARTIAL
        assert state.total_synced == 3
