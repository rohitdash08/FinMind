from datetime import date

import pytest

from app.services.bank_connectors import (
    BankTransaction,
    ConnectorRegistry,
    MockBankConnector,
    default_registry,
    import_bank_transactions,
    refresh_bank_transactions,
)


def test_default_registry_includes_mock_connector():
    registry = default_registry()

    assert registry.names() == ["mock"]
    assert registry.get("MOCK").name == "mock"


def test_import_bank_transactions_uses_connector_and_normalizes_rows():
    registry = ConnectorRegistry()
    registry.register(
        MockBankConnector(
            [
                BankTransaction(
                    date="2026-02-10",
                    amount="-10.50",
                    description="Coffee",
                    currency="USD",
                ),
                BankTransaction(
                    date="2026-02-11",
                    amount=2500.00,
                    description="Payroll Deposit",
                    currency="USD",
                    expense_type="INCOME",
                ),
            ]
        )
    )

    rows = import_bank_transactions(
        connector_name="mock",
        account_id="checking-1",
        registry=registry,
    )

    assert rows == [
        {
            "date": "2026-02-10",
            "amount": 10.5,
            "description": "Coffee",
            "category_id": None,
            "expense_type": "EXPENSE",
            "currency": "USD",
        },
        {
            "date": "2026-02-11",
            "amount": 2500.0,
            "description": "Payroll Deposit",
            "category_id": None,
            "expense_type": "INCOME",
            "currency": "USD",
        },
    ]


def test_import_bank_transactions_supports_date_windows():
    registry = ConnectorRegistry()
    registry.register(
        MockBankConnector(
            [
                {"date": "2026-02-09", "amount": 5, "description": "Before"},
                {"date": "2026-02-10", "amount": 6, "description": "Inside"},
                {"date": "2026-02-12", "amount": 7, "description": "After"},
            ]
        )
    )

    rows = import_bank_transactions(
        connector_name="mock",
        account_id="checking-1",
        since=date(2026, 2, 10),
        until=date(2026, 2, 11),
        registry=registry,
    )

    assert [row["description"] for row in rows] == ["Inside"]


def test_refresh_bank_transactions_uses_connector_refresh_path():
    rows = refresh_bank_transactions(connector_name="mock", account_id="checking-1")

    assert len(rows) == 2
    assert rows[0]["description"] == "Mock Coffee"
    assert rows[1]["expense_type"] == "INCOME"


def test_unknown_connector_and_blank_account_are_rejected():
    with pytest.raises(ValueError, match="unknown bank connector"):
        import_bank_transactions(connector_name="missing", account_id="checking-1")

    with pytest.raises(ValueError, match="account_id required"):
        refresh_bank_transactions(connector_name="mock", account_id=" ")
