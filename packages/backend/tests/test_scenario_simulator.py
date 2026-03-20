"""Tests for Financial Scenario Simulator (What-If Planning) — issue #94."""
import pytest
from unittest.mock import MagicMock

from app.services.scenario_simulator import (
    run_scenario,
    ScenarioSimulationResult,
    ALLOWED_SCENARIO_TYPES,
)


def _make_row(month, tx_type, total):
    row = MagicMock()
    row.month = month
    row.type = tx_type
    row.total = total
    return row


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.all.return_value = rows
    return q


def test_empty_data_returns_result(mocker):
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query([]))
    result = run_scenario(user_id=1, scenario_type="increase_expense", value=100)
    assert isinstance(result, ScenarioSimulationResult)


def test_required_fields_present(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=500)
    assert hasattr(result, "baseline")
    assert hasattr(result, "scenario")
    assert hasattr(result, "net_impact_monthly")
    assert hasattr(result, "net_impact_total")
    assert hasattr(result, "verdict")


def test_increase_income_beneficial(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2500)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=500)
    assert result.verdict == "beneficial"
    assert result.net_impact_monthly > 0


def test_increase_expense_detrimental(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_expense", value=500)
    assert result.verdict == "detrimental"
    assert result.net_impact_monthly < 0


def test_salary_change_positive(mocker):
    rows = [_make_row("2026-01", "income", 4000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="salary_change", value=25)  # 25% raise
    # Income should increase by 25%
    assert result.scenario.monthly_results[0].income > result.baseline.monthly_results[0].income


def test_months_param_projection_count(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=100, months=4)
    assert len(result.scenario.monthly_results) == 4
    assert len(result.baseline.monthly_results) == 4


def test_months_clamped_max(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=100, months=99)
    assert len(result.baseline.monthly_results) == 24


def test_net_impact_total_correct(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=200, months=3)
    # Monthly impact = +200, over 3 months = +600
    assert abs(result.net_impact_total - 600.0) < 1.0


def test_cumulative_net_progressive(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    result = run_scenario(user_id=1, scenario_type="increase_income", value=100, months=3)
    cums = [r.cumulative_net for r in result.scenario.monthly_results]
    # Each month cumulative should be strictly increasing (positive net)
    assert cums[0] < cums[1] < cums[2]


def test_invalid_scenario_type_handled(mocker):
    rows = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    mocker.patch("app.services.scenario_simulator.db.session.query",
                 return_value=_mock_query(rows))
    # Should not raise — falls back to increase_expense
    result = run_scenario(user_id=1, scenario_type="INVALID_TYPE", value=100)
    assert result is not None


def test_reduce_category_decreases_expenses(mocker):
    # First call: averages. Second call: category avg.
    call_count = [0]
    rows_avg = [_make_row("2026-01", "income", 3000), _make_row("2026-01", "expense", 2000)]
    rows_cat = [MagicMock(month="2026-01", total=400)]

    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q

    def all_side_effect():
        call_count[0] += 1
        if call_count[0] <= 1:
            return rows_avg
        return rows_cat

    q.all.side_effect = all_side_effect
    mocker.patch("app.services.scenario_simulator.db.session.query", return_value=q)

    result = run_scenario(
        user_id=1, scenario_type="reduce_category", value=50, category="Dining"
    )
    # 50% reduction of 400 = save 200/month
    assert result.net_impact_monthly > 0
    assert result.verdict in ("beneficial", "neutral")


def test_allowed_scenario_types_constant():
    assert "reduce_category" in ALLOWED_SCENARIO_TYPES
    assert "increase_income" in ALLOWED_SCENARIO_TYPES
    assert "salary_change" in ALLOWED_SCENARIO_TYPES


def test_route_requires_auth(client):
    resp = client.post("/insights/scenario-simulator", json={"scenario_type": "increase_income", "value": 100})
    assert resp.status_code == 401