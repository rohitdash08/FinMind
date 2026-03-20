"""Tests for the Savings Opportunity Detection Engine (#119)."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _add_expense(client, auth_header, amount: float, exp_date: str,
                 category_id: int | None = None, expense_type: str = "EXPENSE"):
    payload = {
        "amount": amount,
        "description": f"Test expense {amount}",
        "date": exp_date,
        "expense_type": expense_type,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = client.post("/expenses", json=payload, headers=auth_header)
    assert r.status_code == 201, f"Expense creation failed: {r.get_json()}"
    return r.get_json()


def _add_category(client, auth_header, name: str) -> int:
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201, f"Category creation failed: {r.get_json()}"
    return r.get_json()["id"]


def _get_opportunities(client, auth_header, month: str):
    r = client.get(
        f"/insights/savings-opportunities?month={month}", headers=auth_header
    )
    return r


# ── Endpoint tests ─────────────────────────────────────────────────────────────

class TestSavingsOpportunitiesEndpoint:
    def test_requires_authentication(self, client):
        r = client.get("/insights/savings-opportunities")
        assert r.status_code == 401

    def test_returns_200_with_valid_token(self, client, auth_header):
        r = _get_opportunities(client, auth_header, "2026-03")
        assert r.status_code == 200

    def test_response_schema(self, client, auth_header):
        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        assert "month" in data
        assert "total_spent" in data
        assert "total_potential_savings" in data
        assert "opportunities_count" in data
        assert "opportunities" in data
        assert isinstance(data["opportunities"], list)

    def test_month_parameter_defaults_to_current_month(self, client, auth_header):
        r = client.get("/insights/savings-opportunities", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["month"] == date.today().strftime("%Y-%m")

    def test_month_parameter_accepted(self, client, auth_header):
        r = _get_opportunities(client, auth_header, "2026-01")
        assert r.status_code == 200
        assert r.get_json()["month"] == "2026-01"

    def test_empty_data_returns_zero_spent(self, client, auth_header):
        r = _get_opportunities(client, auth_header, "2023-01")
        data = r.get_json()
        assert data["total_spent"] == 0.0
        assert data["opportunities_count"] >= 0


# ── Opportunity detection tests ────────────────────────────────────────────────

class TestCategoryOverspend:
    def test_overspend_detected_above_threshold(self, client, auth_header):
        """When spending is 20%+ above 2-month average, rule fires."""
        cat_id = _add_category(client, auth_header, "Dining")
        current = date(2026, 3, 15)
        prior1 = date(2026, 2, 15)
        prior2 = date(2026, 1, 15)

        # Establish baseline: 1000 in Jan, 1000 in Feb
        _add_expense(client, auth_header, 1000.0, prior2.isoformat(), cat_id)
        _add_expense(client, auth_header, 1000.0, prior1.isoformat(), cat_id)

        # Current month: 1500 (50% over average of 1000 → should trigger)
        _add_expense(client, auth_header, 1500.0, current.isoformat(), cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        assert r.status_code == 200
        data = r.get_json()

        rules = [o["rule"] for o in data["opportunities"]]
        assert "category_overspend" in rules

        overspend_ops = [o for o in data["opportunities"] if o["rule"] == "category_overspend"]
        assert len(overspend_ops) >= 1
        op = overspend_ops[0]
        assert op["category"] == "Dining"
        assert op["estimated_savings"] > 0
        assert op["priority"] in ("high", "medium")

    def test_no_overspend_when_within_threshold(self, client, auth_header):
        """Spending exactly at average should not trigger overspend rule."""
        cat_id = _add_category(client, auth_header, "Transport")

        _add_expense(client, auth_header, 500.0, "2026-01-10", cat_id)
        _add_expense(client, auth_header, 500.0, "2026-02-10", cat_id)
        _add_expense(client, auth_header, 500.0, "2026-03-10", cat_id)  # same as avg

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        overspend_ops = [o for o in data["opportunities"] if o["rule"] == "category_overspend"]
        assert len(overspend_ops) == 0


class TestHighFrequency:
    def test_high_frequency_transactions_detected(self, client, auth_header):
        """3+ same-category transactions on a single day should trigger."""
        cat_id = _add_category(client, auth_header, "Coffee")
        target_date = "2026-03-10"

        # 4 coffee purchases on the same day
        for _ in range(4):
            _add_expense(client, auth_header, 50.0, target_date, cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        rules = [o["rule"] for o in data["opportunities"]]
        assert "high_frequency" in rules

    def test_low_frequency_not_flagged(self, client, auth_header):
        """2 transactions per day should NOT trigger high-frequency rule."""
        cat_id = _add_category(client, auth_header, "Snacks")
        target_date = "2026-03-10"

        for _ in range(2):
            _add_expense(client, auth_header, 30.0, target_date, cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        hf_ops = [o for o in data["opportunities"] if o["rule"] == "high_frequency"]
        assert len(hf_ops) == 0


class TestSmallTicketDrain:
    def test_many_small_purchases_flagged(self, client, auth_header):
        """5+ small transactions in a category should trigger small_ticket_drain."""
        cat_id = _add_category(client, auth_header, "Snacks")

        for i in range(6):
            _add_expense(client, auth_header, 80.0, f"2026-03-{10+i:02d}", cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        rules = [o["rule"] for o in data["opportunities"]]
        assert "small_ticket_drain" in rules

    def test_estimated_savings_is_20_percent(self, client, auth_header):
        """Estimated savings for small-ticket drain should be ~20% of total."""
        cat_id = _add_category(client, auth_header, "Impulse")
        total = 0.0
        for i in range(6):
            amount = 100.0
            _add_expense(client, auth_header, amount, f"2026-03-{10+i:02d}", cat_id)
            total += amount

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        ops = [o for o in data["opportunities"] if o["rule"] == "small_ticket_drain"]
        if ops:
            expected = round(total * 0.2, 2)
            assert abs(ops[0]["estimated_savings"] - expected) < 1.0


class TestNoSavingsCategory:
    def test_no_savings_detected_when_no_savings_transactions(self, client, auth_header):
        """If user has no savings/investment category, rule fires."""
        cat_id = _add_category(client, auth_header, "Food")
        _add_expense(client, auth_header, 500.0, "2026-03-10", cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        rules = [o["rule"] for o in data["opportunities"]]
        assert "no_savings_category" in rules

    def test_no_savings_rule_does_not_fire_when_savings_exist(self, client, auth_header):
        """If user has a savings category, no_savings rule should not fire."""
        cat_id = _add_category(client, auth_header, "savings")
        _add_expense(client, auth_header, 200.0, "2026-03-10", cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        rules = [o["rule"] for o in data["opportunities"]]
        assert "no_savings_category" not in rules


class TestOpportunityOrdering:
    def test_high_priority_first(self, client, auth_header):
        """High-priority opportunities must appear before low-priority ones."""
        cat_id = _add_category(client, auth_header, "Dining")

        _add_expense(client, auth_header, 1000.0, "2026-01-10", cat_id)
        _add_expense(client, auth_header, 1000.0, "2026-02-10", cat_id)
        _add_expense(client, auth_header, 2500.0, "2026-03-10", cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        ops = data["opportunities"]

        if len(ops) >= 2:
            priority_order = {"high": 0, "medium": 1, "low": 2}
            for i in range(len(ops) - 1):
                assert priority_order.get(ops[i]["priority"], 3) <= priority_order.get(ops[i+1]["priority"], 3)

    def test_total_potential_savings_sum(self, client, auth_header):
        """total_potential_savings must equal sum of all estimated_savings."""
        cat_id = _add_category(client, auth_header, "Misc")
        _add_expense(client, auth_header, 1000.0, "2026-01-10", cat_id)
        _add_expense(client, auth_header, 1000.0, "2026-02-10", cat_id)
        _add_expense(client, auth_header, 2000.0, "2026-03-10", cat_id)

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        expected = round(sum(o["estimated_savings"] for o in data["opportunities"]), 2)
        assert abs(data["total_potential_savings"] - expected) < 0.01

    def test_opportunity_structure(self, client, auth_header):
        """Each opportunity must have required fields."""
        _add_expense(client, auth_header, 200.0, "2026-03-10")

        r = _get_opportunities(client, auth_header, "2026-03")
        data = r.get_json()
        required = {"id", "title", "description", "category", "estimated_savings", "priority", "rule"}
        for op in data["opportunities"]:
            assert required.issubset(op.keys()), f"Missing fields in: {op}"
