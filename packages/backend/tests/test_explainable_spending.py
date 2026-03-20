"""Tests for Explainable Spending Insights feature (issue #89)."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.explainable_spending import (
    get_spending_insights,
    SpendingInsightsResult,
    SpendingChange,
)


def _make_row(category, total):
    row = MagicMock()
    row.category = category
    row.total = total
    return row


def _mock_query(rows_current=None, rows_previous=None):
    """Return a mock that returns different rows on successive .all() calls."""
    call_count = [0]
    rows_current = rows_current or []
    rows_previous = rows_previous or []

    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q

    def all_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return rows_current
        return rows_previous

    q.all.side_effect = all_side_effect
    return q


def test_empty_returns_zero_confidence(mocker):
    mocker.patch("app.services.explainable_spending.db.session.query", return_value=_mock_query())
    result = get_spending_insights(user_id=1)
    assert result.confidence == 0.0
    assert result.insights == []


def test_empty_message_informative(mocker):
    mocker.patch("app.services.explainable_spending.db.session.query", return_value=_mock_query())
    result = get_spending_insights(user_id=1)
    assert len(result.message if hasattr(result, 'message') else result.summary) > 5


def test_required_fields_present(mocker):
    current = [_make_row("Food", 300)]
    previous = [_make_row("Food", 200)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    assert hasattr(result, "period_current")
    assert hasattr(result, "period_previous")
    assert hasattr(result, "total_current")
    assert hasattr(result, "total_previous")
    assert hasattr(result, "total_change_pct")
    assert hasattr(result, "insights")
    assert hasattr(result, "summary")
    assert hasattr(result, "confidence")


def test_insight_fields_present(mocker):
    current = [_make_row("Food", 300)]
    previous = [_make_row("Food", 200)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    assert len(result.insights) >= 1
    i = result.insights[0]
    assert hasattr(i, "category")
    assert hasattr(i, "current_amount")
    assert hasattr(i, "previous_amount")
    assert hasattr(i, "change_amount")
    assert hasattr(i, "change_pct")
    assert hasattr(i, "explanation")
    assert hasattr(i, "confidence")


def test_change_pct_calculation(mocker):
    current = [_make_row("Rent", 1200)]
    previous = [_make_row("Rent", 1000)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    assert len(result.insights) >= 1
    # Rent went up 20%
    rent_insight = next(i for i in result.insights if i.category == "Rent")
    assert abs(rent_insight.change_pct - 20.0) < 0.1


def test_change_amount_calculation(mocker):
    current = [_make_row("Transport", 150)]
    previous = [_make_row("Transport", 200)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    transport = next((i for i in result.insights if i.category == "Transport"), None)
    if transport:
        assert abs(transport.change_amount - (-50.0)) < 0.01


def test_total_change_pct_correct(mocker):
    current = [_make_row("Food", 1100)]
    previous = [_make_row("Food", 1000)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    assert abs(result.total_change_pct - 10.0) < 0.1


def test_new_category_detected(mocker):
    current = [_make_row("Subscriptions", 50)]
    previous = []  # no prior month data
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    sub = next((i for i in result.insights if i.category == "Subscriptions"), None)
    assert sub is not None
    assert sub.previous_amount == 0.0


def test_vanished_category_detected(mocker):
    current = []
    previous = [_make_row("Gym", 80)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    gym = next((i for i in result.insights if i.category == "Gym"), None)
    assert gym is not None
    assert gym.current_amount == 0.0


def test_insights_sorted_by_absolute_change(mocker):
    current = [_make_row("Food", 500), _make_row("Rent", 1200), _make_row("Gym", 50)]
    previous = [_make_row("Food", 300), _make_row("Rent", 1000), _make_row("Gym", 30)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    changes = [abs(i.change_amount) for i in result.insights]
    assert changes == sorted(changes, reverse=True)


def test_small_changes_filtered_out(mocker):
    current = [_make_row("Coffee", 52)]  # 2 delta
    previous = [_make_row("Coffee", 50)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    # 4% change AND $2 delta — should be filtered (< 5% and <= $10)
    coffee = next((i for i in result.insights if i.category == "Coffee"), None)
    assert coffee is None


def test_month_param_parsed(mocker):
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query())
    result = get_spending_insights(user_id=1, month="2025-06")
    assert result.period_current == "2025-06"
    assert result.period_previous == "2025-05"


def test_january_previous_is_december(mocker):
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query())
    result = get_spending_insights(user_id=1, month="2026-01")
    assert result.period_previous == "2025-12"


def test_confidence_between_0_and_1(mocker):
    current = [_make_row("Food", 300)]
    previous = [_make_row("Food", 200)]
    mocker.patch("app.services.explainable_spending.db.session.query",
                 return_value=_mock_query(current, previous))
    result = get_spending_insights(user_id=1)
    assert 0.0 <= result.confidence <= 1.0


def test_route_requires_auth(client):
    resp = client.get("/insights/spending-insights")
    assert resp.status_code == 401