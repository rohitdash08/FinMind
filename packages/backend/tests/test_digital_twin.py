"""Tests for Personal Financial Digital Twin Simulator."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date, timedelta

from app.services.digital_twin import (
    _get_monthly_averages,
    _risk_assessment,
    run_digital_twin,
    LifeEvent,
    MonthProjection,
    _apply_life_events,
)


def _make_expense(amount=100.0, days_ago=0):
    exp = MagicMock()
    exp.id = 1
    exp.amount = amount
    exp.date = date.today() - timedelta(days=days_ago)
    return exp


def _make_proj(month, net=500, balance=1000):
    return MonthProjection(month=month, income=3000, expenses=2500, net=net, savings_balance=balance, risk_flags=[])


def test_monthly_averages_no_data():
    income, expenses = _get_monthly_averages([], [])
    assert income > 0 and expenses > 0


def test_monthly_averages_with_data():
    expenses = [_make_expense(amount=500, days_ago=i*7) for i in range(8)]
    income, avg = _get_monthly_averages(expenses, [])
    assert income > avg


def test_risk_low_all_positive():
    projs = [_make_proj(f"2026-{i:02d}", net=500, balance=1000+i*500) for i in range(1, 7)]
    risk = _risk_assessment(projs, 3000, 2500)
    assert risk.risk_level in ("low", "medium")


def test_risk_critical_negative_balance():
    projs = [_make_proj(f"2026-{i:02d}", net=-200, balance=-200*i) for i in range(1, 7)]
    risk = _risk_assessment(projs, 3000, 2500)
    assert risk.risk_level in ("high", "critical")


def test_life_event_salary_raise():
    events = [LifeEvent(event_type="salary_raise", month_offset=0, value=20)]
    new_income, _ = _apply_life_events(0, 3000.0, 2500.0, events)
    assert new_income == pytest.approx(3600.0)


def test_life_event_job_loss():
    events = [LifeEvent(event_type="job_loss", month_offset=0, value=50)]
    new_income, _ = _apply_life_events(0, 3000.0, 2500.0, events)
    assert new_income == pytest.approx(1500.0)


def test_life_event_new_expense():
    events = [LifeEvent(event_type="new_expense", month_offset=0, value=200)]
    _, new_exp = _apply_life_events(0, 3000.0, 2500.0, events)
    assert new_exp == pytest.approx(2700.0)


def test_life_event_not_applied_wrong_month():
    events = [LifeEvent(event_type="salary_raise", month_offset=5, value=20)]
    income, _ = _apply_life_events(0, 3000.0, 2500.0, events)
    assert income == 3000.0


def test_projection_length():
    with patch("app.services.digital_twin.Expense") as MockExp, \
         patch("app.services.digital_twin.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = run_digital_twin(1, 6)
        assert len(result.monthly_projections) == 6


def test_projection_months_clamped():
    with patch("app.services.digital_twin.Expense") as MockExp, \
         patch("app.services.digital_twin.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = run_digital_twin(1, 999)
        assert result.projection_months == 120


def test_savings_target():
    with patch("app.services.digital_twin.Expense") as MockExp, \
         patch("app.services.digital_twin.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = run_digital_twin(1, 12, savings_target=1000.0, starting_balance=500.0)
        assert result.savings_outlook is not None


def test_has_risk_assessment():
    with patch("app.services.digital_twin.Expense") as MockExp, \
         patch("app.services.digital_twin.Bill") as MockBill:
        MockExp.query.filter.return_value.all.return_value = []
        MockBill.query.filter.return_value.all.return_value = []
        result = run_digital_twin(1, 3)
        assert result.risk_assessment is not None
        assert result.risk_assessment.risk_level in ("low", "medium", "high", "critical")