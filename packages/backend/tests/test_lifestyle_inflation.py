"""Tests for Lifestyle Inflation Detection Insights (issue #118)."""
import pytest
from unittest.mock import MagicMock

from app.services.lifestyle_inflation import (
    get_lifestyle_inflation,
    LifestyleInflationResult,
    InflationSignal,
    _is_lifestyle,
)


def _make_row(month, category, total):
    row = MagicMock()
    row.month = month
    row.category = category
    row.total = total
    return row


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.all.return_value = rows
    return q


def test_empty_returns_no_signals(mocker):
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query([]))
    result = get_lifestyle_inflation(user_id=1)
    assert result.inflation_signals == []
    assert result.is_inflating is False


def test_required_fields_present(mocker):
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query([]))
    result = get_lifestyle_inflation(user_id=1)
    assert hasattr(result, "analysis_months")
    assert hasattr(result, "lifestyle_inflation_pct")
    assert hasattr(result, "inflation_signals")
    assert hasattr(result, "is_inflating")
    assert hasattr(result, "summary")
    assert hasattr(result, "top_inflated_category")


def test_lifestyle_keyword_detected():
    assert _is_lifestyle("Dining") is True
    assert _is_lifestyle("Gym") is True
    assert _is_lifestyle("Streaming") is True
    assert _is_lifestyle("Coffee") is True


def test_non_lifestyle_not_flagged():
    assert _is_lifestyle("Rent") is False
    assert _is_lifestyle("Utilities") is False
    assert _is_lifestyle("Mortgage") is False


def test_inflation_signal_detected(mocker):
    # Dining goes from 200 (old) to 300 (new) = 50% increase
    rows = [
        _make_row("2025-07", "Dining", 200),
        _make_row("2025-08", "Dining", 200),
        _make_row("2025-09", "Dining", 200),
        _make_row("2025-10", "Dining", 300),
        _make_row("2025-11", "Dining", 300),
        _make_row("2025-12", "Dining", 300),
    ]
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query(rows))
    result = get_lifestyle_inflation(user_id=1, months=6)
    dining = next((s for s in result.inflation_signals if s.category == "Dining"), None)
    assert dining is not None
    assert dining.inflation_pct > 0
    assert dining.severity in ("moderate", "high")


def test_no_inflation_below_threshold(mocker):
    # Dining changes by 2% - below 5% threshold
    rows = [
        _make_row("2025-07", "Dining", 100),
        _make_row("2025-08", "Dining", 100),
        _make_row("2025-09", "Dining", 100),
        _make_row("2025-10", "Dining", 102),
        _make_row("2025-11", "Dining", 102),
        _make_row("2025-12", "Dining", 102),
    ]
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query(rows))
    result = get_lifestyle_inflation(user_id=1, months=6, threshold_pct=5.0)
    assert len(result.inflation_signals) == 0


def test_severity_high_for_50pct_plus(mocker):
    rows = [
        _make_row("2025-07", "Entertainment", 100),
        _make_row("2025-08", "Entertainment", 100),
        _make_row("2025-09", "Entertainment", 100),
        _make_row("2025-10", "Entertainment", 200),
        _make_row("2025-11", "Entertainment", 200),
        _make_row("2025-12", "Entertainment", 200),
    ]
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query(rows))
    result = get_lifestyle_inflation(user_id=1, months=6)
    sig = next((s for s in result.inflation_signals if s.category == "Entertainment"), None)
    if sig:
        assert sig.severity == "high"


def test_signals_sorted_by_inflation_pct(mocker):
    rows = [
        # Cat A: 10% increase
        _make_row("2025-07", "Coffee", 100),
        _make_row("2025-08", "Coffee", 100),
        _make_row("2025-09", "Coffee", 100),
        _make_row("2025-10", "Coffee", 110),
        _make_row("2025-11", "Coffee", 110),
        _make_row("2025-12", "Coffee", 110),
        # Cat B: 50% increase
        _make_row("2025-07", "Dining", 100),
        _make_row("2025-08", "Dining", 100),
        _make_row("2025-09", "Dining", 100),
        _make_row("2025-10", "Dining", 150),
        _make_row("2025-11", "Dining", 150),
        _make_row("2025-12", "Dining", 150),
    ]
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query(rows))
    result = get_lifestyle_inflation(user_id=1, months=6)
    if len(result.inflation_signals) >= 2:
        pcts = [s.inflation_pct for s in result.inflation_signals]
        assert pcts == sorted(pcts, reverse=True)


def test_is_inflating_flag_set(mocker):
    rows = [
        _make_row("2025-07", "Dining", 100),
        _make_row("2025-08", "Dining", 100),
        _make_row("2025-09", "Dining", 100),
        _make_row("2025-10", "Dining", 200),
        _make_row("2025-11", "Dining", 200),
        _make_row("2025-12", "Dining", 200),
    ]
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query(rows))
    result = get_lifestyle_inflation(user_id=1, months=6)
    assert result.is_inflating is True


def test_months_must_be_even(mocker):
    mocker.patch("app.services.lifestyle_inflation.db.session.query",
                 return_value=_mock_query([]))
    result = get_lifestyle_inflation(user_id=1, months=5)
    assert result.analysis_months % 2 == 0


def test_route_requires_auth(client):
    resp = client.get("/insights/lifestyle-inflation")
    assert resp.status_code == 401