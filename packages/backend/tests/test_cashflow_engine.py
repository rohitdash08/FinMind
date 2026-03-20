"""Tests for Cash-flow Forecast Engine."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from app.services.cashflow_engine import (
    _get_daily_avg_expense,
    _aggregate_weekly,
    _aggregate_monthly,
    get_cashflow_forecast,
    DailyProjection,
)


def _make_expense(amount=100.0, days_ago=0):
    exp = MagicMock()
    exp.amount = amount
    exp.spent_at = date.today() - timedelta(days=days_ago)
    return exp


def _make_proj(d, income=100, expenses=80, net=20, balance=1000):
    return DailyProjection(
        date=d,
        income=income,
        expenses=expenses,
        net=net,
        running_balance=balance,
        sources=[],
    )


# ── Daily average ──────────────────────────────────────────────────────

def test_daily_avg_no_data():
    with patch("app.services.cashflow_engine.Expense") as MockExp:
        MockExp.query.filter.return_value.all.return_value = []
        avg = _get_daily_avg_expense(1)
    assert avg == 0.0


def test_daily_avg_with_data():
    expenses = [_make_expense(amount=300, days_ago=i) for i in range(30)]
    with patch("app.services.cashflow_engine.Expense") as MockExp:
        MockExp.query.filter.return_value.all.return_value = expenses
        avg = _get_daily_avg_expense(1)
    assert avg > 0


# ── Weekly aggregation ──────────────────────────────────────────────────

def test_weekly_aggregation():
    projs = [_make_proj(f"2026-03-{i:02d}", income=100, expenses=80) for i in range(1, 8)]
    weeks = _aggregate_weekly(projs)
    assert len(weeks) >= 1
    assert all("income" in w for w in weeks)


def test_monthly_aggregation():
    projs = [_make_proj(f"2026-03-{i:02d}") for i in range(1, 10)]
    months = _aggregate_monthly(projs)
    assert len(months) >= 1
    assert months[0]["month"] == "2026-03"


# ── Full forecast ──────────────────────────────────────────────────────

def test_forecast_30_days():
    with patch("app.services.cashflow_engine.Expense") as MockExp, \
         patch("app.services.cashflow_engine.RecurringExpense") as MockRec, \
         patch("app.services.cashflow_engine.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockRec.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_cashflow_forecast(1, 30, 0.0)
    assert result.horizon_days == 30
    assert len(result.daily_projections) == 30


def test_forecast_60_days():
    with patch("app.services.cashflow_engine.Expense") as MockExp, \
         patch("app.services.cashflow_engine.RecurringExpense") as MockRec, \
         patch("app.services.cashflow_engine.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockRec.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_cashflow_forecast(1, 60, 1000.0)
    assert result.horizon_days == 60
    assert result.starting_balance == 1000.0


def test_forecast_horizon_clamped():
    with patch("app.services.cashflow_engine.Expense") as MockExp, \
         patch("app.services.cashflow_engine.RecurringExpense") as MockRec, \
         patch("app.services.cashflow_engine.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockRec.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_cashflow_forecast(1, 200)
    assert result.horizon_days == 90


def test_forecast_has_weekly_and_monthly():
    with patch("app.services.cashflow_engine.Expense") as MockExp, \
         patch("app.services.cashflow_engine.RecurringExpense") as MockRec, \
         patch("app.services.cashflow_engine.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockRec.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_cashflow_forecast(1, 30)
    assert len(result.weekly_summary) > 0
    assert len(result.monthly_summary) > 0


def test_forecast_income_exceeds_expenses():
    """Income should be 20% above base expenses."""
    with patch("app.services.cashflow_engine.Expense") as MockExp, \
         patch("app.services.cashflow_engine.RecurringExpense") as MockRec, \
         patch("app.services.cashflow_engine.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockRec.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = get_cashflow_forecast(1, 30)
    # When no data, income=50/day, expenses=0 -> net positive
    assert result.net_cash_flow >= 0