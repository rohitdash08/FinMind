"""Tests for Autonomous Budget Optimization feature (issue #92)."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.budget_optimization import (
    get_budget_optimization,
    BudgetOptimizationResult,
    CategoryRecommendation,
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


def test_empty_returns_empty_result(mocker):
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query([]))
    result = get_budget_optimization(user_id=1)
    assert result.recommendations == []
    assert result.total_potential_savings == 0.0
    assert result.months_analyzed == 0


def test_empty_summary_informative(mocker):
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query([]))
    result = get_budget_optimization(user_id=1)
    assert len(result.summary) > 10


def test_required_fields_present(mocker):
    rows = [_make_row("2026-01", "Food", 300)]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    assert hasattr(result, "total_monthly_avg")
    assert hasattr(result, "total_suggested_budget")
    assert hasattr(result, "total_potential_savings")
    assert hasattr(result, "recommendations")
    assert hasattr(result, "reallocations")
    assert hasattr(result, "summary")
    assert hasattr(result, "months_analyzed")


def test_recommendation_fields_present(mocker):
    rows = [_make_row("2026-01", "Dining", 200)]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    assert len(result.recommendations) >= 1
    r = result.recommendations[0]
    assert hasattr(r, "category")
    assert hasattr(r, "current_avg")
    assert hasattr(r, "suggested_budget")
    assert hasattr(r, "potential_saving")
    assert hasattr(r, "overspending")
    assert hasattr(r, "recommendation")
    assert hasattr(r, "priority")


def test_essential_category_no_reduction(mocker):
    rows = [_make_row("2026-01", "Rent", 1000)]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    rent = next((r for r in result.recommendations if r.category == "Rent"), None)
    assert rent is not None
    assert rent.potential_saving == 0.0
    assert rent.priority == "low"


def test_lifestyle_category_gets_reduction(mocker):
    rows = [_make_row("2026-01", "Dining", 400)]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    dining = next((r for r in result.recommendations if r.category == "Dining"), None)
    assert dining is not None
    assert dining.suggested_budget < dining.current_avg
    assert dining.potential_saving > 0


def test_discretionary_category_25pct_reduction(mocker):
    rows = [_make_row("2026-01", "Hobbies", 200)]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    hobbies = next((r for r in result.recommendations if r.category == "Hobbies"), None)
    assert hobbies is not None
    # Discretionary = 25% reduction
    assert abs(hobbies.suggested_budget - 150.0) < 1.0
    assert abs(hobbies.potential_saving - 50.0) < 1.0


def test_overspending_flag_for_growing_lifestyle(mocker):
    # Dining growing from 200 to 250 — is_growing = recent > avg * 1.1
    rows = [
        _make_row("2026-01", "Dining", 100),
        _make_row("2026-02", "Dining", 200),
        _make_row("2026-03", "Dining", 300),
    ]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    dining = next((r for r in result.recommendations if r.category == "Dining"), None)
    assert dining is not None
    assert dining.overspending is True
    assert dining.priority == "high"


def test_high_priority_items_come_first(mocker):
    rows = [
        _make_row("2026-01", "Rent", 1000),
        _make_row("2026-01", "Dining", 400),
        _make_row("2026-01", "Hobbies", 200),
    ]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    priorities = [r.priority for r in result.recommendations]
    # All "high" or "medium" items should appear before "low" items
    seen_low = False
    for p in priorities:
        if p == "low":
            seen_low = True
        elif seen_low:
            pytest.fail(f"Non-low priority item found after low: {p}")


def test_total_potential_savings_sum_correct(mocker):
    rows = [
        _make_row("2026-01", "Gym", 100),
        _make_row("2026-01", "Hobbies", 200),
    ]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    calculated = sum(r.potential_saving for r in result.recommendations)
    assert abs(result.total_potential_savings - calculated) < 0.01


def test_reallocations_built_for_top_savers(mocker):
    rows = [
        _make_row("2026-01", "Entertainment", 500),
        _make_row("2026-01", "Hobbies", 300),
        _make_row("2026-01", "Dining", 200),
        _make_row("2026-01", "Rent", 1000),
    ]
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query(rows))
    result = get_budget_optimization(user_id=1)
    # Should have reallocations for categories with savings
    assert len(result.reallocations) >= 1
    for rl in result.reallocations:
        assert rl.to_category == "savings"
        assert rl.suggested_amount > 0


def test_months_param_clamped(mocker):
    mocker.patch("app.services.budget_optimization.db.session.query",
                 return_value=_mock_query([]))
    result = get_budget_optimization(user_id=1, months=99)
    # months clamped to 12 max — should not error
    assert result is not None


def test_route_requires_auth(client):
    resp = client.get("/insights/budget-optimization")
    assert resp.status_code == 401