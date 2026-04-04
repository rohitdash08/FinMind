"""Tests for the Smart Digest (weekly financial summary) feature."""

from datetime import date, timedelta

import pytest


# ---------------------------------------------------------------------------
# Helper: seed transactions for a specific date range
# ---------------------------------------------------------------------------


def _seed_expense(client, auth_header, amount, description, dt, expense_type="EXPENSE", category_id=None):
    payload = {
        "amount": amount,
        "description": description,
        "date": dt.isoformat(),
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"seed expense failed: {r.get_json()}"
    return r.get_json()


def _seed_bill(client, auth_header, name, amount, due_date):
    r = client.post(
        "/bills",
        json={
            "name": name,
            "amount": amount,
            "next_due_date": due_date.isoformat(),
            "cadence": "WEEKLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201, f"seed bill failed: {r.get_json()}"
    return r.get_json()


def _monday_of_current_week() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


# ---------------------------------------------------------------------------
# parse_week_param unit tests
# ---------------------------------------------------------------------------


class TestParseWeekParam:
    def test_none_returns_current_week(self):
        from app.services.smart_digest import parse_week_param

        iso_year, iso_week = parse_week_param(None)
        today = date.today()
        expected_year, expected_week, _ = today.isocalendar()
        assert iso_year == expected_year
        assert iso_week == expected_week

    def test_empty_string_returns_current_week(self):
        from app.services.smart_digest import parse_week_param

        iso_year, iso_week = parse_week_param("")
        today = date.today()
        expected_year, expected_week, _ = today.isocalendar()
        assert iso_year == expected_year
        assert iso_week == expected_week

    def test_valid_week_string(self):
        from app.services.smart_digest import parse_week_param

        iso_year, iso_week = parse_week_param("2026-W14")
        assert iso_year == 2026
        assert iso_week == 14

    def test_valid_single_digit_week(self):
        from app.services.smart_digest import parse_week_param

        iso_year, iso_week = parse_week_param("2026-W3")
        assert iso_year == 2026
        assert iso_week == 3

    def test_invalid_format_raises(self):
        from app.services.smart_digest import parse_week_param

        with pytest.raises(ValueError, match="Invalid week format"):
            parse_week_param("2026-14")

    def test_invalid_week_number_raises(self):
        from app.services.smart_digest import parse_week_param

        with pytest.raises(ValueError, match="Week number must be 1-53"):
            parse_week_param("2026-W0")

    def test_week_54_raises(self):
        from app.services.smart_digest import parse_week_param

        with pytest.raises(ValueError, match="Week number must be 1-53"):
            parse_week_param("2026-W54")


# ---------------------------------------------------------------------------
# week_bounds unit tests
# ---------------------------------------------------------------------------


class TestWeekBounds:
    def test_known_week(self):
        from app.services.smart_digest import _week_bounds

        start, end = _week_bounds(2026, 1)
        # 2026-W01 starts on Monday 2025-12-29
        assert start == date(2025, 12, 29)
        assert end == date(2026, 1, 4)

    def test_week_bounds_span_seven_days(self):
        from app.services.smart_digest import _week_bounds

        start, end = _week_bounds(2026, 14)
        assert (end - start).days == 6
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6    # Sunday


# ---------------------------------------------------------------------------
# Integration tests — /digest/weekly endpoint
# ---------------------------------------------------------------------------


class TestWeeklyDigestEndpoint:
    def test_returns_digest_structure(self, client, auth_header):
        """Verify the response payload contains all required fields."""
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        # Top-level keys
        assert "period" in payload
        assert "summary" in payload
        assert "category_breakdown" in payload
        assert "daily_spending" in payload
        assert "top_transactions" in payload
        assert "upcoming_bills" in payload
        assert "insights" in payload
        assert "method" in payload

        # Period metadata
        assert "iso_year" in payload["period"]
        assert "iso_week" in payload["period"]
        assert "start_date" in payload["period"]
        assert "end_date" in payload["period"]

        # Summary fields
        assert "total_income" in payload["summary"]
        assert "total_expenses" in payload["summary"]
        assert "net_flow" in payload["summary"]
        assert "week_over_week_change_pct" in payload["summary"]

        # Insights
        assert "highlights" in payload["insights"]
        assert "saving_tip" in payload["insights"]

    def test_returns_data_for_current_week(self, client, auth_header):
        """Seed expenses in the current week and verify they appear."""
        monday = _monday_of_current_week()

        _seed_expense(client, auth_header, 5000, "Salary", monday, "INCOME")
        _seed_expense(client, auth_header, 200, "Groceries", monday)
        _seed_expense(client, auth_header, 100, "Transport", monday + timedelta(days=1))

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()

        assert payload["summary"]["total_income"] >= 5000
        assert payload["summary"]["total_expenses"] >= 300
        assert payload["summary"]["net_flow"] >= 4700

    def test_specific_week_param(self, client, auth_header):
        """Verify that specifying a week parameter returns that week's data."""
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        week_str = f"{iso_year}-W{iso_week:02d}"

        monday = _monday_of_current_week()
        _seed_expense(client, auth_header, 150, "Coffee", monday)

        r = client.get(f"/digest/weekly?week={week_str}", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["period"]["iso_year"] == iso_year
        assert payload["period"]["iso_week"] == iso_week
        assert payload["summary"]["total_expenses"] >= 150

    def test_invalid_week_returns_400(self, client, auth_header):
        r = client.get("/digest/weekly?week=bad-format", headers=auth_header)
        assert r.status_code == 400
        assert "error" in r.get_json()

    def test_category_breakdown_included(self, client, auth_header):
        """Verify category breakdown is populated when expenses exist."""
        r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
        assert r.status_code == 201
        food_id = r.get_json()["id"]

        monday = _monday_of_current_week()
        _seed_expense(client, auth_header, 250, "Lunch", monday, category_id=food_id)

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert len(payload["category_breakdown"]) >= 1
        food_cat = next(
            (c for c in payload["category_breakdown"] if c["category_name"] == "Food"),
            None,
        )
        assert food_cat is not None
        assert food_cat["amount"] >= 250

    def test_daily_spending_populated(self, client, auth_header):
        monday = _monday_of_current_week()
        _seed_expense(client, auth_header, 50, "Day1", monday)
        _seed_expense(client, auth_header, 75, "Day2", monday + timedelta(days=1))

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert len(payload["daily_spending"]) >= 2

    def test_top_transactions_limited(self, client, auth_header):
        monday = _monday_of_current_week()
        for i in range(7):
            _seed_expense(client, auth_header, (i + 1) * 10, f"Txn{i}", monday)

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert len(payload["top_transactions"]) <= 5
        # Verify descending order by amount
        amounts = [t["amount"] for t in payload["top_transactions"]]
        assert amounts == sorted(amounts, reverse=True)

    def test_upcoming_bills_in_week(self, client, auth_header):
        monday = _monday_of_current_week()
        _seed_bill(client, auth_header, "Internet", 49.99, monday + timedelta(days=3))

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["summary"]["upcoming_bills_count"] >= 1
        assert payload["summary"]["upcoming_bills_total"] >= 49.99

    def test_week_over_week_change(self, client, auth_header):
        """Seed expenses in two consecutive weeks and verify WoW change."""
        monday = _monday_of_current_week()
        prev_monday = monday - timedelta(days=7)

        _seed_expense(client, auth_header, 100, "Last week", prev_monday)
        _seed_expense(client, auth_header, 200, "This week", monday)

        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        # 200 vs 100 => 100% increase
        assert payload["summary"]["week_over_week_change_pct"] == 100.0

    def test_heuristic_method_without_gemini(self, client, auth_header):
        """Without Gemini key, method should be heuristic."""
        r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["method"] == "heuristic"

    def test_gemini_key_triggers_gemini_method(self, client, auth_header, monkeypatch):
        """When user supplies Gemini key, the Gemini path is invoked."""
        captured = {}

        def _fake_gemini(summary_data, api_key, model, persona):
            captured["api_key"] = api_key
            return {
                "highlights": ["AI insight 1", "AI insight 2"],
                "risk_flag": None,
                "saving_tip": "AI tip",
            }

        monkeypatch.setattr(
            "app.services.smart_digest._gemini_insights", _fake_gemini
        )

        r = client.get(
            "/digest/weekly",
            headers={**auth_header, "X-Gemini-Api-Key": "user-key-123"},
        )
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["method"] == "gemini"
        assert captured["api_key"] == "user-key-123"
        assert "AI insight 1" in payload["insights"]["highlights"]

    def test_gemini_failure_falls_back_to_heuristic(self, client, auth_header, monkeypatch):
        """When Gemini fails, fallback to heuristic with a warning."""

        def _boom(*_args, **_kwargs):
            raise RuntimeError("gemini down")

        monkeypatch.setattr(
            "app.services.smart_digest._gemini_insights", _boom
        )

        r = client.get(
            "/digest/weekly",
            headers={**auth_header, "X-Gemini-Api-Key": "user-key-123"},
        )
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["method"] == "heuristic"
        assert "warnings" in payload
        assert "gemini_unavailable" in payload["warnings"]

    def test_empty_week_returns_valid_digest(self, client, auth_header):
        """A week with no transactions should still return a valid digest."""
        r = client.get("/digest/weekly?week=2020-W01", headers=auth_header)
        assert r.status_code == 200
        payload = r.get_json()
        assert payload["summary"]["total_income"] == 0
        assert payload["summary"]["total_expenses"] == 0
        assert payload["summary"]["net_flow"] == 0
        assert payload["insights"]["highlights"]  # should have at least one

    def test_requires_authentication(self, client):
        """Endpoint should reject unauthenticated requests."""
        r = client.get("/digest/weekly")
        assert r.status_code in (401, 422)


# ---------------------------------------------------------------------------
# Heuristic insights unit tests
# ---------------------------------------------------------------------------


class TestHeuristicInsights:
    def test_positive_cash_flow(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 1000,
            "total_expenses": 500,
            "week_over_week_change_pct": 0,
            "category_breakdown": [],
        })
        assert any("Positive cash flow" in h for h in result["highlights"])
        assert result["risk_flag"] is None

    def test_overspending_risk(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 200,
            "total_expenses": 500,
            "week_over_week_change_pct": 0,
            "category_breakdown": [],
        })
        assert result["risk_flag"] is not None
        assert "exceeded" in result["risk_flag"].lower()

    def test_spending_increase_warning(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 1000,
            "total_expenses": 500,
            "week_over_week_change_pct": 50,
            "category_breakdown": [],
        })
        assert any("increased" in h.lower() for h in result["highlights"])

    def test_spending_decrease_praise(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 1000,
            "total_expenses": 500,
            "week_over_week_change_pct": -20,
            "category_breakdown": [],
        })
        assert any("decreased" in h.lower() for h in result["highlights"])

    def test_top_category_mentioned(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 1000,
            "total_expenses": 500,
            "week_over_week_change_pct": 0,
            "category_breakdown": [
                {"category_name": "Food", "share_pct": 60, "amount": 300},
                {"category_name": "Transport", "share_pct": 40, "amount": 200},
            ],
        })
        assert any("Food" in h for h in result["highlights"])
        assert "Food" in result["saving_tip"]

    def test_no_transactions(self):
        from app.services.smart_digest import _heuristic_insights

        result = _heuristic_insights({
            "total_income": 0,
            "total_expenses": 0,
            "week_over_week_change_pct": 0,
            "category_breakdown": [],
        })
        assert any("No transactions" in h for h in result["highlights"])
