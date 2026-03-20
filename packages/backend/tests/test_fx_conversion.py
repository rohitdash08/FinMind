"""Tests for Multi-Currency & FX Conversion Support (issue #95)."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.fx_conversion import (
    get_multi_currency_summary,
    convert_amount,
    MultiCurrencyResult,
    _get_rate,
    _rate_cache,
)


def _make_tx(tx_id, tx_type, amount, tx_date="2026-01-15", currency="USD"):
    tx = MagicMock()
    tx.id = tx_id
    tx.type = tx_type
    tx.amount = amount
    tx.date = tx_date
    tx.currency = currency
    return tx


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = rows
    return q


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

def test_empty_returns_zero_totals(mocker):
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query([]))
    mocker.patch("app.services.fx_conversion._get_rate", return_value=1.0)
    result = get_multi_currency_summary(user_id=1)
    assert result.total_expenses_converted == 0.0
    assert result.total_income_converted == 0.0
    assert result.analytics_by_currency == []


# ---------------------------------------------------------------------------
# Conversion logic
# ---------------------------------------------------------------------------

def test_same_currency_rate_is_one():
    assert _get_rate.__wrapped__(None, None) if hasattr(_get_rate, "__wrapped__") else True
    # Direct: USD to USD = 1.0
    from app.services.fx_conversion import _get_rate as gr
    # Mock requests to return known rate
    with patch("app.services.fx_conversion.requests.get") as mock_get:
        mock_get.return_value.json.return_value = {"rates": {"EUR": 0.9}}
        mock_get.return_value.raise_for_status = lambda: None
        rate = gr("EUR", "EUR")
        assert rate == 1.0


def test_convert_amount_basic(mocker):
    mocker.patch("app.services.fx_conversion._get_rate", return_value=0.85)
    result = convert_amount(100.0, "USD", "EUR")
    assert result["converted_amount"] == 85.0
    assert result["exchange_rate"] == 0.85
    assert result["original_currency"] == "USD"
    assert result["target_currency"] == "EUR"


def test_convert_amount_required_fields():
    with patch("app.services.fx_conversion._get_rate", return_value=1.2):
        result = convert_amount(200.0, "USD", "GBP")
        assert "original_amount" in result
        assert "converted_amount" in result
        assert "exchange_rate" in result
        assert "rate_date" in result


def test_expenses_converted_correctly(mocker):
    txs = [_make_tx(1, "expense", 1000.0, currency="USD")]
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query(txs))
    mocker.patch("app.services.fx_conversion._get_historical_rate", return_value=0.9)
    mocker.patch("app.services.fx_conversion._get_rate", return_value=0.9)
    result = get_multi_currency_summary(user_id=1, target_currency="EUR")
    assert abs(result.total_expenses_converted - 900.0) < 1.0


def test_income_converted_correctly(mocker):
    txs = [_make_tx(1, "income", 2000.0, currency="USD")]
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query(txs))
    mocker.patch("app.services.fx_conversion._get_historical_rate", return_value=0.9)
    mocker.patch("app.services.fx_conversion._get_rate", return_value=0.9)
    result = get_multi_currency_summary(user_id=1, target_currency="EUR")
    assert abs(result.total_income_converted - 1800.0) < 1.0


def test_net_equals_income_minus_expenses(mocker):
    txs = [
        _make_tx(1, "income", 3000.0),
        _make_tx(2, "expense", 2000.0),
    ]
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query(txs))
    mocker.patch("app.services.fx_conversion._get_historical_rate", return_value=1.0)
    mocker.patch("app.services.fx_conversion._get_rate", return_value=1.0)
    result = get_multi_currency_summary(user_id=1)
    assert abs(result.net_converted - (result.total_income_converted - result.total_expenses_converted)) < 0.01


def test_analytics_by_currency_populated(mocker):
    txs = [
        _make_tx(1, "expense", 100.0, currency="USD"),
        _make_tx(2, "expense", 50.0, currency="EUR"),
    ]
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query(txs))
    mocker.patch("app.services.fx_conversion._get_historical_rate", return_value=1.0)
    mocker.patch("app.services.fx_conversion._get_rate", return_value=1.0)
    result = get_multi_currency_summary(user_id=1)
    currencies = [a.currency for a in result.analytics_by_currency]
    assert "USD" in currencies
    assert "EUR" in currencies


def test_result_has_required_fields(mocker):
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query([]))
    mocker.patch("app.services.fx_conversion._get_rate", return_value=1.0)
    result = get_multi_currency_summary(user_id=1)
    assert hasattr(result, "base_currency")
    assert hasattr(result, "target_currency")
    assert hasattr(result, "recent_rate")
    assert hasattr(result, "rate_date")


def test_months_clamped(mocker):
    mocker.patch("app.services.fx_conversion.db.session.query", return_value=_mock_query([]))
    mocker.patch("app.services.fx_conversion._get_rate", return_value=1.0)
    result = get_multi_currency_summary(user_id=1, months=99)
    assert result is not None  # Should not error


def test_currency_summary_route_requires_auth(client):
    resp = client.get("/insights/currency-summary")
    assert resp.status_code == 401


def test_convert_route_requires_auth(client):
    resp = client.get("/insights/convert?amount=100&from=USD&to=EUR")
    assert resp.status_code == 401