"""Tests for the weekly financial digest service and API endpoint."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from app.services.insights import (
    get_weekly_expense_summary,
    get_weekly_bill_summary,
    generate_insights,
    build_weekly_digest,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_expense(amount, category, days_ago=1, user_id=1):
    e = MagicMock()
    e.amount = amount
    e.category = category
    e.date = datetime.utcnow() - timedelta(days=days_ago)
    e.user_id = user_id
    return e


def _make_bill(amount, is_paid, days_ago=1, user_id=1):
    b = MagicMock()
    b.amount = amount
    b.is_paid = is_paid
    b.due_date = datetime.utcnow() - timedelta(days=days_ago)
    b.user_id = user_id
    return b


def _db_with_expenses(expenses):
    db = MagicMock()
    query_mock = MagicMock()
    db.query.return_value = query_mock
    query_mock.filter.return_value = query_mock
    query_mock.all.return_value = expenses
    return db


# ---------------------------------------------------------------------------
# get_weekly_expense_summary
# ---------------------------------------------------------------------------

class TestGetWeeklyExpenseSummary:
    def test_empty_returns_zero_totals(self):
        db = _db_with_expenses([])
        result = get_weekly_expense_summary(db, user_id=1)
        assert result["total_spent"] == 0.0
        assert result["transaction_count"] == 0
        assert result["by_category"] == {}
        assert result["top_categories"] == []

    def test_single_expense(self):
        expenses = [_make_expense(50.0, "Food")]
        db = _db_with_expenses(expenses)
        result = get_weekly_expense_summary(db, user_id=1)
        assert result["total_spent"] == 50.0
        assert result["transaction_count"] == 1
        assert result["by_category"] == {"Food": 50.0}

    def test_multiple_categories(self):
        expenses = [
            _make_expense(100.0, "Food"),
            _make_expense(200.0, "Transport"),
            _make_expense(50.0, "Food"),
        ]
        db = _db_with_expenses(expenses)
        result = get_weekly_expense_summary(db, user_id=1)
        assert result["total_spent"] == 350.0
        assert result["by_category"]["Food"] == 150.0
        assert result["by_category"]["Transport"] == 200.0

    def test_top_categories_limited_to_three(self):
        expenses = [
            _make_expense(10, "A"),
            _make_expense(20, "B"),
            _make_expense(30, "C"),
            _make_expense(40, "D"),
        ]
        db = _db_with_expenses(expenses)
        result = get_weekly_expense_summary(db, user_id=1)
        assert len(result["top_categories"]) == 3
        assert result["top_categories"][0]["category"] == "D"

    def test_period_dates_present(self):
        db = _db_with_expenses([])
        result = get_weekly_expense_summary(db, user_id=1)
        assert "period_start" in result
        assert "period_end" in result


# ---------------------------------------------------------------------------
# get_weekly_bill_summary
# ---------------------------------------------------------------------------

class TestGetWeeklyBillSummary:
    def test_empty(self):
        db = _db_with_expenses([])  # returns empty list for bills too
        result = get_weekly_bill_summary(db, user_id=1)
        assert result["total_bills"] == 0
        assert result["total_due"] == 0.0
        assert result["paid_count"] == 0
        assert result["unpaid_count"] == 0
        assert result["unpaid_amount"] == 0.0

    def test_paid_and_unpaid(self):
        bills = [
            _make_bill(100.0, is_paid=True),
            _make_bill(200.0, is_paid=False),
            _make_bill(50.0, is_paid=False),
        ]
        db = _db_with_expenses(bills)
        result = get_weekly_bill_summary(db, user_id=1)
        assert result["total_bills"] == 3
        assert result["total_due"] == 350.0
        assert result["paid_count"] == 1
        assert result["unpaid_count"] == 2
        assert result["unpaid_amount"] == 250.0


# ---------------------------------------------------------------------------
# generate_insights
# ---------------------------------------------------------------------------

class TestGenerateInsights:
    def _expense_summary(self, total=0.0, count=0, top_categories=None):
        return {
            "total_spent": total,
            "transaction_count": count,
            "top_categories": top_categories or [],
            "by_category": {},
            "period_start": "2024-01-01",
            "period_end": "2024-01-07",
        }

    def _bill_summary(self, total_bills=0, total_due=0.0, paid=0, unpaid=0, unpaid_amount=0.0):
        return {
            "total_bills": total_bills,
            "total_due": total_due,
            "paid_count": paid,
            "unpaid_count": unpaid,
            "unpaid_amount": unpaid_amount,
        }

    def test_no_expenses_insight(self):
        insights = generate_insights(self._expense_summary(), self._bill_summary())
        assert any("No expenses" in i for i in insights)

    def test_spending_total_insight(self):
        summary = self._expense_summary(total=123.45, count=3)
        insights = generate_insights(summary, self._bill_summary())
        assert any("123.45" in i for i in insights)

    def test_top_category_insight(self):
        summary = self._expense_summary(
            total=200.0,
            count=2,
            top_categories=[{"category": "Dining", "amount": 150.0}],
        )
        insights = generate_insights(summary, self._bill_summary())
        assert any("Dining" in i for i in insights)

    def test_week_over_week_increase(self):
        current = self._expense_summary(total=200.0, count=5)
        previous = self._expense_summary(total=100.0, count=4)
        insights = generate_insights(current, self._bill_summary(), previous_expense_summary=previous)
        assert any("up" in i and "100.0%" in i for i in insights)

    def test_week_over_week_decrease(self):
        current = self._expense_summary(total=50.0, count=2)
        previous = self._expense_summary(total=100.0, count=5)
        insights = generate_insights(current, self._bill_summary(), previous_expense_summary=previous)
        assert any("down" in i for i in insights)

    def test_unpaid_bills_insight(self):
        bills = self._bill_summary(total_bills=2, total_due=300.0, paid=0, unpaid=2, unpaid_amount=300.0)
        insights = generate_insights(self._expense_summary(), bills)
        assert any("unpaid" in i.lower() for i in insights)

    def test_all_bills_paid_insight(self):
        bills = self._bill_summary(total_bills=2, total_due=200.0, paid=2, unpaid=0, unpaid_amount=0.0)
        insights = generate_insights(self._expense_summary(), bills)
        assert any("paid" in i.lower() for i in insights)

    def test_no_previous_data_skips_trend(self):
        current = self._expense_summary(total=100.0, count=3)
        insights = generate_insights(current, self._bill_summary(), previous_expense_summary=None)
        assert not any("compared to last week" in i for i in insights)

    def test_previous_zero_total_skips_trend(self):
        current = self._expense_summary(total=100.0, count=3)
        previous = self._expense_summary(total=0.0, count=0)
        insights = generate_insights(current, self._bill_summary(), previous_expense_summary=previous)
        assert not any("compared to last week" in i for i in insights)


# ---------------------------------------------------------------------------
# build_weekly_digest
# ---------------------------------------------------------------------------

class TestBuildWeeklyDigest:
    def test_digest_structure(self):
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.all.return_value = []

        digest = build_weekly_digest(db, user_id=42)

        assert digest["user_id"] == 42
        assert "generated_at" in digest
        assert "expense_summary" in digest
        assert "previous_week_expense_summary" in digest
        assert "bill_summary" in digest
        assert "insights" in digest
        assert isinstance(digest["insights"], list)

    def test_digest_generated_at_is_recent(self):
        db = MagicMock()
        query_mock = MagicMock()
        db.query.return_value = query_mock
        query_mock.filter.return_value = query_mock
        query_mock.all.return_value = []

        digest = build_weekly_digest(db, user_id=1)
        generated = datetime.fromisoformat(digest["generated_at"])
        assert (datetime.utcnow() - generated).total_seconds() < 5


# ---------------------------------------------------------------------------
# API endpoint (integration-style with TestClient)
# ---------------------------------------------------------------------------

try:
    from fastapi.testclient import TestClient
    from app.main import app
    from app import dependencies

    _HAS_APP = True
except Exception:  # pragma: no cover
    _HAS_APP = False


@pytest.mark.skipif(not _HAS_APP, reason="FastAPI app not importable in this environment")
class TestWeeklyDigestEndpoint:
    def _get_client(self, fake_user, fake_digest):
        with patch.object(dependencies, "get_current_user", return_value=fake_user), \
             patch("app.routes.insights.build_weekly_digest", return_value=fake_digest):
            client = TestClient(app)
            return client, fake_digest

    def test_returns_200_with_digest(self):
        fake_user = MagicMock(id=1)
        fake_digest = {
            "generated_at": datetime.utcnow().isoformat(),
            "user_id": 1,
            "expense_summary": {},
            "previous_week_expense_summary": {},
            "bill_summary": {},
            "insights": ["Test insight"],
        }
        client, expected = self._get_client(fake_user, fake_digest)
        response = client.get("/insights/weekly-digest")
        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == 1
        assert data["insights"] == ["Test insight"]
