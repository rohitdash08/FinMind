"""
Tests for BankConnector — runs without any external services.
pytest packages/backend/tests/test_bank_connector.py
"""

import pytest
from datetime import date, timedelta

from app.services.bank_connector import (
    MockConnector,
    ConsentStatus,
    TransactionType,
    get_connector,
    register_connector,
    BankConnector,
)


@pytest.fixture
def mock():
    return MockConnector()


@pytest.fixture
def handle(mock):
    h = mock.initiate_consent("user-1", "http://localhost/callback")
    return mock.confirm_consent(h, {})


# ── initiate_consent ──────────────────────────────────────────────────────────

def test_initiate_consent_returns_handle(mock):
    handle = mock.initiate_consent("user-1", "http://localhost/callback")
    assert handle.handle_id.startswith("mock-handle-")
    assert "mock=true" in handle.redirect_url
    assert handle.status == ConsentStatus.PENDING


# ── confirm_consent ───────────────────────────────────────────────────────────

def test_confirm_consent_activates(mock, handle):
    assert handle.status == ConsentStatus.ACTIVE
    assert handle.artefact_id is not None


# ── fetch_accounts ────────────────────────────────────────────────────────────

def test_fetch_accounts_returns_list(mock, handle):
    accounts = mock.fetch_accounts(handle)
    assert len(accounts) == 1
    acc = accounts[0]
    assert acc.account_id == "mock-acc-001"
    assert acc.currency == "INR"
    assert acc.account_type == "SAVINGS"


# ── import_transactions ───────────────────────────────────────────────────────

def test_import_transactions_returns_data(mock, handle):
    from_date = date(2024, 1, 1)
    to_date = date(2024, 1, 31)
    txns = mock.import_transactions(handle, "mock-acc-001", from_date, to_date)
    assert len(txns) > 0


def test_import_transactions_types(mock, handle):
    from_date = date(2024, 1, 1)
    to_date = date(2024, 3, 31)
    txns = mock.import_transactions(handle, "mock-acc-001", from_date, to_date)
    for txn in txns:
        assert txn.transaction_type in (TransactionType.DEBIT, TransactionType.CREDIT)
        assert txn.amount > 0
        assert txn.currency == "INR"
        assert from_date <= txn.date <= to_date


def test_import_transactions_unique_ids(mock, handle):
    from_date = date(2024, 1, 1)
    to_date = date(2024, 1, 31)
    txns = mock.import_transactions(handle, "mock-acc-001", from_date, to_date)
    ids = [t.transaction_id for t in txns]
    assert len(ids) == len(set(ids)), "Transaction IDs must be unique"


# ── refresh ───────────────────────────────────────────────────────────────────

def test_refresh_returns_recent_transactions(mock, handle):
    last_synced = date.today() - timedelta(days=7)
    txns = mock.refresh(handle, "mock-acc-001", last_synced)
    assert isinstance(txns, list)
    for txn in txns:
        assert txn.date >= last_synced


# ── registry ─────────────────────────────────────────────────────────────────

def test_get_connector_mock():
    connector = get_connector("mock")
    assert isinstance(connector, MockConnector)


def test_get_connector_unknown_raises():
    with pytest.raises(ValueError, match="Unknown bank provider"):
        get_connector("nonexistent_bank")


def test_register_custom_connector():
    class DummyConnector(BankConnector):
        provider_name = "Dummy"
        def initiate_consent(self, *a, **kw): pass
        def confirm_consent(self, *a, **kw): pass
        def fetch_accounts(self, *a, **kw): return []
        def import_transactions(self, *a, **kw): return []
        def refresh(self, *a, **kw): return []

    register_connector("dummy", DummyConnector)
    assert isinstance(get_connector("dummy"), DummyConnector)
