"""Tests for Universal Bank Statement Normalization Layer (issue #112)."""
import pytest

from app.services.bank_normalization import (
    normalize_bank_statement,
    NormalizationResult,
    NormalizedTransaction,
    _normalize_date,
    _detect_category,
    _clean_description,
)


def test_empty_rows_returns_empty(client):
    result = normalize_bank_statement(rows=[])
    assert result.normalized == []
    assert result.total_rows == 0


def test_required_result_fields():
    result = normalize_bank_statement(rows=[])
    assert hasattr(result, "normalized")
    assert hasattr(result, "rejected")
    assert hasattr(result, "total_rows")
    assert hasattr(result, "success_count")
    assert hasattr(result, "rejection_count")
    assert hasattr(result, "detected_format")
    assert hasattr(result, "summary")


def test_iso_date_parsed():
    assert _normalize_date("2026-01-15") == "2026-01-15"


def test_us_date_parsed():
    assert _normalize_date("01/15/2026") == "2026-01-15"


def test_invalid_date_returns_none():
    assert _normalize_date("not-a-date") is None


def test_single_amount_negative_is_expense():
    rows = [{"date": "2026-01-15", "description": "Walmart", "amount": -50.0}]
    result = normalize_bank_statement(rows)
    assert len(result.normalized) == 1
    assert result.normalized[0].type == "expense"
    assert result.normalized[0].amount == 50.0


def test_single_amount_positive_is_income():
    rows = [{"date": "2026-01-15", "description": "Payroll deposit", "amount": 3000.0}]
    result = normalize_bank_statement(rows)
    assert len(result.normalized) == 1
    assert result.normalized[0].type == "income"


def test_debit_credit_columns():
    rows = [
        {"date": "2026-01-15", "description": "Coffee", "debit": 5.0, "credit": ""},
        {"date": "2026-01-16", "description": "Payroll", "debit": "", "credit": 3000.0},
    ]
    result = normalize_bank_statement(rows, debit_field="debit", credit_field="credit")
    types = [n.type for n in result.normalized]
    assert "expense" in types
    assert "income" in types


def test_category_hint_grocery():
    cat = _detect_category("Walmart grocery purchase")
    assert cat == "groceries"


def test_category_hint_dining():
    cat = _detect_category("Starbucks Coffee")
    assert cat == "dining"


def test_category_hint_transport():
    cat = _detect_category("Uber ride")
    assert cat == "transport"


def test_bad_date_row_rejected():
    rows = [{"date": "INVALID", "description": "test", "amount": 100}]
    result = normalize_bank_statement(rows)
    assert result.rejection_count == 1
    assert result.success_count == 0


def test_description_cleaned():
    cleaned = _clean_description("  Payment #REF12345678   ")
    assert "  " not in cleaned


def test_normalized_transaction_fields():
    rows = [{"date": "2026-01-15", "description": "Restaurant Sushi", "amount": 45.0}]
    result = normalize_bank_statement(rows)
    n = result.normalized[0]
    assert hasattr(n, "date")
    assert hasattr(n, "description")
    assert hasattr(n, "amount")
    assert hasattr(n, "type")
    assert hasattr(n, "currency")
    assert hasattr(n, "category_hint")


def test_route_requires_auth(client):
    resp = client.post("/insights/normalize-statement", json={"rows": []})
    assert resp.status_code == 401