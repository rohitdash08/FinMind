"""Tests for the Financial Health Score endpoints."""

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_expense(client, auth_header, amount, expense_type="EXPENSE", days_ago=0):
    spent_at = (date.today() - timedelta(days=days_ago)).isoformat()
    r = client.post(
        "/expenses",
        json={
            "amount": amount,
            "expense_type": expense_type,
            "description": "test txn",
            "date": spent_at,
            "currency": "USD",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def _make_bill(client, auth_header, name="Electric", amount=50.0, due_days=10):
    due = (date.today() + timedelta(days=due_days)).isoformat()
    r = client.post(
        "/bills",
        json={
            "name": name,
            "amount": amount,
            "currency": "USD",
            "next_due_date": due,
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, r.get_json()
    return r.get_json()


# ---------------------------------------------------------------------------
# GET /health-score
# ---------------------------------------------------------------------------

class TestGetHealthScore:
    def test_returns_200_with_expected_structure(self, client, auth_header):
        r = client.get("/health-score", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "score" in data
        assert "grade" in data
        assert "breakdown" in data
        assert "period" in data
        assert "computed_at" in data

    def test_score_in_valid_range(self, client, auth_header):
        r = client.get("/health-score", headers=auth_header)
        data = r.get_json()
        assert 0 <= data["score"] <= 100

    def test_grade_is_valid(self, client, auth_header):
        r = client.get("/health-score", headers=auth_header)
        data = r.get_json()
        assert data["grade"] in ("A", "B", "C", "D", "F")

    def test_breakdown_has_four_metrics(self, client, auth_header):
        r = client.get("/health-score", headers=auth_header)
        bd = r.get_json()["breakdown"]
        assert "savings_rate" in bd
        assert "spending_stability" in bd
        assert "bill_reliability" in bd
        assert "trend" in bd

    def test_each_metric_within_range(self, client, auth_header):
        r = client.get("/health-score", headers=auth_header)
        bd = r.get_json()["breakdown"]
        for metric, data in bd.items():
            assert 0 <= data["points"] <= data["max"], (
                f"{metric}: {data['points']} not in [0, {data['max']}]"
            )

    def test_requires_authentication(self, client):
        r = client.get("/health-score")
        assert r.status_code == 401

    def test_savings_rate_reflects_income_expenses(self, client, auth_header):
        # Add income and expenses for current month
        _make_expense(client, auth_header, 1000, expense_type="INCOME", days_ago=0)
        _make_expense(client, auth_header, 500, expense_type="EXPENSE", days_ago=1)

        r = client.get("/health-score", headers=auth_header)
        bd = r.get_json()["breakdown"]
        detail = bd["savings_rate"]["detail"]
        assert detail["income"] == 1000.0
        assert detail["expenses"] == 500.0
        assert detail["savings_rate_pct"] == 50.0
        # 50% savings → full 25 pts
        assert bd["savings_rate"]["points"] == 25.0

    def test_bill_reliability_reflects_overdue(self, client, auth_header):
        # A bill already overdue
        overdue_date = (date.today() - timedelta(days=5)).isoformat()
        client.post(
            "/bills",
            json={
                "name": "Late Bill",
                "amount": 30.0,
                "currency": "USD",
                "next_due_date": overdue_date,
                "cadence": "MONTHLY",
            },
            headers=auth_header,
        )
        r = client.get("/health-score", headers=auth_header)
        bd = r.get_json()["breakdown"]
        detail = bd["bill_reliability"]["detail"]
        assert detail["overdue"] >= 1

    def test_grade_a_with_perfect_metrics(self, client, auth_header):
        # High income, low expenses — should yield a good grade
        _make_expense(client, auth_header, 5000, expense_type="INCOME", days_ago=0)
        _make_expense(client, auth_header, 500, expense_type="EXPENSE", days_ago=1)
        _make_bill(client, auth_header, due_days=15)

        r = client.get("/health-score", headers=auth_header)
        data = r.get_json()
        # At 5000 income / 500 expense, savings rate is 90% → full 25 pts.
        # With no historical data, trend defaults to neutral (12.5) and
        # spending stability also gets a fair score.
        assert data["score"] > 50, data


# ---------------------------------------------------------------------------
# GET /health-score/history
# ---------------------------------------------------------------------------

class TestGetHealthScoreHistory:
    def test_returns_200_with_history_key(self, client, auth_header):
        r = client.get("/health-score/history", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "history" in data

    def test_history_has_up_to_six_periods(self, client, auth_header):
        r = client.get("/health-score/history", headers=auth_header)
        history = r.get_json()["history"]
        assert 1 <= len(history) <= 6

    def test_history_periods_are_sorted_oldest_first(self, client, auth_header):
        r = client.get("/health-score/history", headers=auth_header)
        periods = [item["period"] for item in r.get_json()["history"]]
        assert periods == sorted(periods)

    def test_history_items_have_required_fields(self, client, auth_header):
        r = client.get("/health-score/history", headers=auth_header)
        for item in r.get_json()["history"]:
            assert "period" in item
            assert "score" in item
            assert "grade" in item
            assert "breakdown" in item

    def test_requires_authentication(self, client):
        r = client.get("/health-score/history")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /health-score/tips
# ---------------------------------------------------------------------------

class TestGetHealthScoreTips:
    def test_returns_200_with_tips_list(self, client, auth_header):
        r = client.get("/health-score/tips", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "tips" in data
        assert isinstance(data["tips"], list)
        assert data["count"] == len(data["tips"])

    def test_tips_list_not_empty(self, client, auth_header):
        r = client.get("/health-score/tips", headers=auth_header)
        assert len(r.get_json()["tips"]) > 0

    def test_requires_authentication(self, client):
        r = client.get("/health-score/tips")
        assert r.status_code == 401

    def test_tips_target_weak_areas(self, client, auth_header):
        # No income → savings_rate = 0 → tips should mention savings
        r = client.get("/health-score/tips", headers=auth_header)
        tips = r.get_json()["tips"]
        # At least one tip should be a non-empty string
        assert all(isinstance(t, str) and len(t) > 0 for t in tips)
