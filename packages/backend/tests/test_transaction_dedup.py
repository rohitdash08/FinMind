"""Tests for Transaction Deduplication Intelligence (issue #113)."""
import pytest
from unittest.mock import MagicMock
from datetime import date

from app.services.transaction_dedup import (
    detect_duplicates,
    DeduplicationResult,
    DuplicateGroup,
    _normalize_description,
)


def _make_tx(tx_id, amount, tx_date, category="Food", tx_type="expense", description=""):
    tx = MagicMock()
    tx.id = tx_id
    tx.amount = amount
    tx.date = tx_date
    tx.category = category
    tx.type = tx_type
    tx.description = description
    return tx


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.all.return_value = rows
    return q


def test_empty_returns_no_duplicates(mocker):
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query([]))
    result = detect_duplicates(user_id=1)
    assert result.duplicate_groups == []
    assert result.total_duplicates_found == 0


def test_required_fields_present(mocker):
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query([]))
    result = detect_duplicates(user_id=1)
    assert hasattr(result, "duplicate_groups")
    assert hasattr(result, "total_duplicates_found")
    assert hasattr(result, "estimated_duplicate_amount")
    assert hasattr(result, "summary")


def test_exact_duplicate_detected(mocker):
    txs = [
        _make_tx(1, 100.0, date(2026, 1, 15)),
        _make_tx(2, 100.0, date(2026, 1, 15)),  # exact duplicate
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    assert len(result.duplicate_groups) >= 1
    assert result.total_duplicates_found >= 1


def test_exact_duplicate_high_confidence(mocker):
    txs = [
        _make_tx(1, 150.0, date(2026, 1, 10)),
        _make_tx(2, 150.0, date(2026, 1, 10)),
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    if result.duplicate_groups:
        assert result.duplicate_groups[0].confidence >= 0.9


def test_duplicate_group_fields_present(mocker):
    txs = [
        _make_tx(1, 200.0, date(2026, 1, 5)),
        _make_tx(2, 200.0, date(2026, 1, 5)),
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    if result.duplicate_groups:
        g = result.duplicate_groups[0]
        assert hasattr(g, "transaction_ids")
        assert hasattr(g, "confidence")
        assert hasattr(g, "reason")
        assert hasattr(g, "suggested_keep_id")
        assert hasattr(g, "amounts")
        assert hasattr(g, "dates")


def test_suggested_keep_is_oldest(mocker):
    txs = [
        _make_tx(5, 100.0, date(2026, 1, 15)),
        _make_tx(3, 100.0, date(2026, 1, 15)),  # lower id = earlier
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    if result.duplicate_groups:
        assert result.duplicate_groups[0].suggested_keep_id == 3


def test_near_date_duplicate_detected(mocker):
    txs = [
        _make_tx(1, 100.0, date(2026, 1, 15)),
        _make_tx(2, 100.0, date(2026, 1, 17)),  # 2 days later, same amount
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1, days_window=2)
    assert len(result.duplicate_groups) >= 1


def test_near_date_outside_window_not_flagged(mocker):
    txs = [
        _make_tx(1, 100.0, date(2026, 1, 15)),
        _make_tx(2, 100.0, date(2026, 1, 20)),  # 5 days later, outside window=2
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1, days_window=2)
    assert len(result.duplicate_groups) == 0


def test_different_amounts_not_duplicates(mocker):
    txs = [
        _make_tx(1, 100.0, date(2026, 1, 15)),
        _make_tx(2, 200.0, date(2026, 1, 15)),  # different amount
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    assert len(result.duplicate_groups) == 0


def test_estimated_amount_correct(mocker):
    txs = [
        _make_tx(1, 100.0, date(2026, 1, 15)),
        _make_tx(2, 100.0, date(2026, 1, 15)),  # duplicate
    ]
    mocker.patch("app.services.transaction_dedup.db.session.query",
                 return_value=_mock_query(txs))
    result = detect_duplicates(user_id=1)
    # 1 duplicate of $100 = estimated_amount = $100
    assert abs(result.estimated_duplicate_amount - 100.0) < 0.01


def test_normalize_description_removes_numbers():
    normalized = _normalize_description("Payment ref 12345")
    assert "12345" not in normalized
    assert "N" in normalized


def test_route_requires_auth(client):
    resp = client.get("/insights/deduplication")
    assert resp.status_code == 401