"""Tests for the Advanced Cash Flow Forecasting feature (issue #93)."""
import pytest
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

from app.services.cash_flow_forecast import (
    get_cash_flow_forecast,
    CashFlowForecastResult,
    MonthlyProjection,
    IrregularExpense,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_row(month, tx_type, total):
    row = MagicMock()
    row.month = month
    row.type = tx_type
    row.total = total
    return row


def _mock_query(rows):
    """Return a mock that returns `rows` from .all()."""
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.all.return_value = rows
    return q


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

def test_empty_returns_stable(mocker):
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query([]))
    result = get_cash_flow_forecast(user_id=1)
    assert isinstance(result, CashFlowForecastResult)
    assert result.monthly_projections == []
    assert result.trend == "stable"
    assert result.overall_confidence == 0.0


def test_empty_message_informative(mocker):
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query([]))
    result = get_cash_flow_forecast(user_id=1)
    assert len(result.message) > 10


# ---------------------------------------------------------------------------
# Projection count
# ---------------------------------------------------------------------------

def test_default_3_projections(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    assert len(result.monthly_projections) == 3


def test_forecast_months_param(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1, forecast_months=5)
    assert len(result.monthly_projections) == 5


def test_forecast_months_clamped_max(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1, forecast_months=99)
    assert len(result.monthly_projections) == 6


def test_forecast_months_clamped_min(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1, forecast_months=0)
    assert len(result.monthly_projections) == 1


# ---------------------------------------------------------------------------
# Projection fields
# ---------------------------------------------------------------------------

def test_projection_has_required_fields(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    p = result.monthly_projections[0]
    assert hasattr(p, "month")
    assert hasattr(p, "projected_income")
    assert hasattr(p, "projected_expenses")
    assert hasattr(p, "projected_net")
    assert hasattr(p, "confidence")


def test_projected_net_equals_income_minus_expenses(mocker):
    rows = [_make_row("2026-01", "income", 4000), _make_row("2026-01", "expense", 2500)]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    p = result.monthly_projections[0]
    assert abs(p.projected_net - (p.projected_income - p.projected_expenses)) < 0.01


def test_confidence_decays_over_months(mocker):
    rows = [
        _make_row("2026-01", "income", 3000),
        _make_row("2026-02", "income", 3000),
        _make_row("2026-03", "income", 3000),
        _make_row("2026-01", "expense", 2000),
        _make_row("2026-02", "expense", 2000),
        _make_row("2026-03", "expense", 2000),
    ]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1, forecast_months=3)
    confs = [p.confidence for p in result.monthly_projections]
    # Each month confidence should be <= previous
    assert confs[0] >= confs[1] >= confs[2]


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------

def test_trend_improving_detected(mocker):
    # Recent 3 months net > older 3 months net (net improving)
    rows = [
        # older months (worse)
        _make_row("2025-07", "income", 1000),
        _make_row("2025-07", "expense", 900),
        _make_row("2025-08", "income", 1000),
        _make_row("2025-08", "expense", 900),
        _make_row("2025-09", "income", 1000),
        _make_row("2025-09", "expense", 900),
        # recent months (better)
        _make_row("2025-10", "income", 2000),
        _make_row("2025-10", "expense", 500),
        _make_row("2025-11", "income", 2000),
        _make_row("2025-11", "expense", 500),
        _make_row("2025-12", "income", 2000),
        _make_row("2025-12", "expense", 500),
    ]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    assert result.trend == "improving"


def test_trend_declining_detected(mocker):
    rows = [
        # older months (better)
        _make_row("2025-07", "income", 2000),
        _make_row("2025-07", "expense", 500),
        _make_row("2025-08", "income", 2000),
        _make_row("2025-08", "expense", 500),
        _make_row("2025-09", "income", 2000),
        _make_row("2025-09", "expense", 500),
        # recent months (worse)
        _make_row("2025-10", "income", 1000),
        _make_row("2025-10", "expense", 950),
        _make_row("2025-11", "income", 1000),
        _make_row("2025-11", "expense", 950),
        _make_row("2025-12", "income", 1000),
        _make_row("2025-12", "expense", 950),
    ]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    assert result.trend == "declining"


# ---------------------------------------------------------------------------
# Averages
# ---------------------------------------------------------------------------

def test_avg_monthly_income_correct(mocker):
    rows = [
        _make_row("2026-01", "income", 1000),
        _make_row("2026-02", "income", 3000),
    ]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    assert abs(result.avg_monthly_income - 2000.0) < 0.01


def test_avg_monthly_expenses_correct(mocker):
    rows = [
        _make_row("2026-01", "expense", 800),
        _make_row("2026-02", "expense", 1200),
    ]
    mocker.patch("app.services.cash_flow_forecast.db.session.query", return_value=_mock_query(rows))
    result = get_cash_flow_forecast(user_id=1)
    assert abs(result.avg_monthly_expenses - 1000.0) < 0.01


# ---------------------------------------------------------------------------
# Route auth
# ---------------------------------------------------------------------------

def test_route_requires_auth(client):
    resp = client.get("/insights/cash-flow-forecast")
    assert resp.status_code == 401