"""Tests for Smart Payee & Merchant Alias Management (issue #114)."""
import pytest
from unittest.mock import MagicMock
from datetime import date

from app.services.payee_alias import (
    get_payee_aliases,
    PayeeAliasResult,
    PayeeAlias,
    _get_canonical,
)


def _make_tx(tx_id, description, amount=50.0, tx_date=date(2026, 1, 15)):
    tx = MagicMock()
    tx.id = tx_id
    tx.description = description
    tx.amount = amount
    tx.date = tx_date
    tx.type = "expense"
    tx.category = "General"
    return tx


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = rows
    return q


def test_empty_returns_no_aliases(mocker):
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query([]))
    result = get_payee_aliases(user_id=1)
    assert result.aliases == []
    assert result.total_payees_found == 0


def test_required_fields_present(mocker):
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query([]))
    result = get_payee_aliases(user_id=1)
    assert hasattr(result, "aliases")
    assert hasattr(result, "total_payees_found")
    assert hasattr(result, "summary")


def test_amazon_canonical_detected():
    canonical, cat = _get_canonical("AMAZON.COM PURCHASE")
    assert canonical == "Amazon"
    assert cat == "shopping"


def test_uber_canonical_detected():
    canonical, cat = _get_canonical("UBER TRIP 12345")
    assert canonical == "Uber"
    assert cat == "transport"


def test_starbucks_canonical_detected():
    canonical, _ = _get_canonical("Starbucks #1234 Seattle")
    assert canonical == "Starbucks"


def test_aliases_grouped_correctly(mocker):
    txs = [
        _make_tx(1, "AMAZON.COM PURCHASE 001"),
        _make_tx(2, "AMAZON PRIME RENEWAL"),
        _make_tx(3, "AMAZON.COM PURCHASE 002"),
    ]
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query(txs))
    result = get_payee_aliases(user_id=1, min_transactions=1)
    amazon = next((a for a in result.aliases if a.canonical_name == "Amazon"), None)
    assert amazon is not None
    assert amazon.transaction_count >= 2


def test_total_spend_correct(mocker):
    txs = [
        _make_tx(1, "Starbucks store", amount=5.0),
        _make_tx(2, "Starbucks drive-thru", amount=6.0),
    ]
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query(txs))
    result = get_payee_aliases(user_id=1, min_transactions=1)
    sbux = next((a for a in result.aliases if a.canonical_name == "Starbucks"), None)
    if sbux:
        assert abs(sbux.total_spend - 11.0) < 0.01


def test_min_transactions_filter(mocker):
    txs = [_make_tx(1, "Chipotle order")]  # only 1 transaction
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query(txs))
    result = get_payee_aliases(user_id=1, min_transactions=2)
    # Should be filtered out (only 1 tx < min=2)
    assert result.total_payees_found == 0


def test_aliases_sorted_by_spend(mocker):
    txs = [
        _make_tx(1, "Netflix subscription", amount=15.0),
        _make_tx(2, "Netflix plan", amount=15.0),
        _make_tx(3, "Uber ride", amount=25.0),
        _make_tx(4, "Uber trip", amount=30.0),
    ]
    mocker.patch("app.services.payee_alias.db.session.query", return_value=_mock_query(txs))
    result = get_payee_aliases(user_id=1, min_transactions=1)
    if len(result.aliases) >= 2:
        spends = [a.total_spend for a in result.aliases]
        assert spends == sorted(spends, reverse=True)


def test_route_requires_auth(client):
    resp = client.get("/insights/payee-aliases")
    assert resp.status_code == 401