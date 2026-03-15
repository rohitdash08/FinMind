"""Tests for the guided monthly financial review feature."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import (
    Expense,
    Category,
    Bill,
    BillCadence,
    RecurringExpense,
    RecurringCadence,
)


# ── Helpers ───────────────────────────────────────────────────────


def _seed_category(user_id, name):
    cat = Category(user_id=user_id, name=name)
    db.session.add(cat)
    db.session.flush()
    return cat


def _seed_expense(user_id, amount, spent_at, category_id=None, notes="", expense_type="EXPENSE"):
    e = Expense(
        user_id=user_id,
        amount=Decimal(str(amount)),
        spent_at=spent_at,
        category_id=category_id,
        notes=notes,
        expense_type=expense_type,
        currency="INR",
    )
    db.session.add(e)
    db.session.flush()
    return e


def _seed_bill(user_id, name, amount, due_date, autopay=False):
    b = Bill(
        user_id=user_id,
        name=name,
        amount=Decimal(str(amount)),
        next_due_date=due_date,
        cadence=BillCadence.MONTHLY,
        autopay_enabled=autopay,
    )
    db.session.add(b)
    db.session.flush()
    return b


def _seed_recurring(user_id, notes, amount, cadence="MONTHLY"):
    r = RecurringExpense(
        user_id=user_id,
        notes=notes,
        amount=Decimal(str(amount)),
        cadence=RecurringCadence(cadence),
        start_date=date(2026, 1, 1),
        active=True,
    )
    db.session.add(r)
    db.session.flush()
    return r


def _seed_standard_data(user_id):
    """Seed a standard set of test data for March 2026."""
    cat_food = _seed_category(user_id, "Food")
    cat_transport = _seed_category(user_id, "Transport")

    # March expenses — mix of types
    _seed_expense(user_id, 500, date(2026, 3, 1), cat_food.id, "Groceries")
    _seed_expense(user_id, 200, date(2026, 3, 5), cat_transport.id, "Uber")
    _seed_expense(user_id, 300, date(2026, 3, 10), cat_food.id, "Dinner")
    _seed_expense(user_id, 150, date(2026, 3, 15), None, "Misc")
    _seed_expense(user_id, 1000, date(2026, 3, 20), cat_food.id, "Party")
    _seed_expense(user_id, 5000, date(2026, 3, 7), None, "Salary", expense_type="INCOME")
    # Weekend expense (March 7 is Saturday, March 8 is Sunday)
    _seed_expense(user_id, 400, date(2026, 3, 7), cat_food.id, "Weekend brunch")
    _seed_expense(user_id, 250, date(2026, 3, 8), cat_transport.id, "Weekend trip")

    # February expenses for comparison
    _seed_expense(user_id, 800, date(2026, 2, 10), cat_food.id, "Feb food")
    _seed_expense(user_id, 300, date(2026, 2, 15), cat_transport.id, "Feb transport")

    # Bills due in March
    _seed_bill(user_id, "Rent", 10000, date(2026, 3, 1), autopay=True)
    _seed_bill(user_id, "Internet", 500, date(2026, 3, 15), autopay=False)

    # Recurring expenses
    _seed_recurring(user_id, "Netflix", 200, "MONTHLY")
    _seed_recurring(user_id, "Gym membership", 12000, "YEARLY")

    db.session.commit()
    return {"cat_food": cat_food, "cat_transport": cat_transport}


# ── Service Tests ─────────────────────────────────────────────────


class TestGetReview:
    def test_returns_seven_steps(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            user_id = 1
            _seed_standard_data(user_id)

        from app.services.monthly_review import get_review

        with app_fixture.app_context():
            result = get_review(1, 2026, 3)
            assert result["year"] == 2026
            assert result["month"] == 3
            assert len(result["steps"]) == 7
            # Each step has step number, title, description, data
            for i, step in enumerate(result["steps"], 1):
                assert step["step"] == i
                assert "title" in step
                assert "description" in step
                assert "data" in step


class TestSpendingSummary:
    def test_calculates_totals(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 1)
            data = result["data"]
            # Total spending = 500+200+300+150+1000+400+250 = 2800
            assert data["total_spending"] == 2800.0
            assert data["total_income"] == 5000.0
            assert data["net"] == 2200.0
            # Count = 8 (7 expenses + 1 income)
            assert data["transaction_count"] == 8
            assert data["highest_single"] == 1000.0
            assert data["lowest_single"] == 150.0

    def test_empty_month(self, app_fixture, auth_header, client):
        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 6, 1)
            data = result["data"]
            assert data["total_spending"] == 0
            assert data["transaction_count"] == 0


class TestCategoryBreakdown:
    def test_categories_sorted_by_amount(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 2)
            data = result["data"]
            cats = data["categories"]
            assert len(cats) >= 2
            # Food = 500+300+1000+400 = 2200, Transport = 200+250 = 450, Uncategorized = 150
            assert cats[0]["category"] == "Food"
            assert cats[0]["amount"] == 2200.0
            # Verify sorted descending
            for i in range(len(cats) - 1):
                assert cats[i]["amount"] >= cats[i + 1]["amount"]
            # Percentages sum to ~100
            total_pct = sum(c["percentage"] for c in cats)
            assert 99.0 <= total_pct <= 101.0

    def test_top_category(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 2)
            assert result["data"]["top_category"] == "Food"


class TestTopExpenses:
    def test_returns_top_ten(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 3)
            expenses = result["data"]["expenses"]
            # Should be sorted by amount desc, excludes income
            assert len(expenses) <= 10
            assert expenses[0]["amount"] == 1000.0
            for i in range(len(expenses) - 1):
                assert expenses[i]["amount"] >= expenses[i + 1]["amount"]

    def test_expense_fields(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 3)
            e = result["data"]["expenses"][0]
            assert "id" in e
            assert "amount" in e
            assert "notes" in e
            assert "spent_at" in e
            assert "currency" in e


class TestBillSummary:
    def test_bills_due_in_month(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 4)
            data = result["data"]
            assert data["bill_count"] == 2
            assert data["autopay_count"] == 1
            assert data["manual_count"] == 1
            assert data["total_bills"] == 10500.0

    def test_bill_fields(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 4)
            bill = result["data"]["bills"][0]
            assert "id" in bill
            assert "name" in bill
            assert "amount" in bill
            assert "due_date" in bill
            assert "autopay" in bill


class TestRecurringSummary:
    def test_monthly_normalization(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 5)
            data = result["data"]
            assert data["count"] == 2
            # Netflix 200/mo + Gym 12000/yr=1000/mo = 1200 total
            assert data["total_monthly"] == 1200.0

    def test_recurring_item_fields(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 5)
            item = result["data"]["items"][0]
            assert "id" in item
            assert "notes" in item
            assert "amount" in item
            assert "cadence" in item
            assert "monthly_equivalent" in item

    def test_sorted_by_monthly_equivalent(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 5)
            items = result["data"]["items"]
            for i in range(len(items) - 1):
                assert items[i]["monthly_equivalent"] >= items[i + 1]["monthly_equivalent"]


class TestMonthComparison:
    def test_compares_with_previous_month(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 6)
            data = result["data"]
            # March spending = 2800, Feb spending = 1100
            assert data["current_month_total"] == 2800.0
            assert data["previous_month_total"] == 1100.0
            assert data["change_amount"] == 1700.0
            assert data["trend"] == "up"
            assert data["change_pct"] > 0

    def test_january_compares_with_december(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_expense(1, 100, date(2026, 1, 5), notes="Jan expense")
            _seed_expense(1, 200, date(2025, 12, 10), notes="Dec expense")
            db.session.commit()

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 1, 6)
            data = result["data"]
            assert data["current_month_total"] == 100.0
            assert data["previous_month_total"] == 200.0
            assert data["trend"] == "down"


class TestInsights:
    def test_peak_spending_day(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 7)
            insights = result["data"]["insights"]
            peak = next((i for i in insights if i["type"] == "peak_spending_day"), None)
            assert peak is not None
            assert peak["value"] > 0

    def test_category_concentration(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 7)
            insights = result["data"]["insights"]
            conc = next((i for i in insights if i["type"] == "category_concentration"), None)
            # Food is 2200/2800 = 78.6% > 50%, so should trigger
            assert conc is not None
            assert conc["value"] > 50

    def test_no_insights_for_empty_month(self, app_fixture, auth_header, client):
        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 6, 7)
            assert result["data"]["insight_count"] == 0


class TestGetAvailableMonths:
    def test_returns_months_with_data(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_available_months

        with app_fixture.app_context():
            result = get_available_months(1)
            # Should have March and February 2026
            assert len(result) >= 2
            months = [(r["year"], r["month"]) for r in result]
            assert (2026, 3) in months
            assert (2026, 2) in months

    def test_sorted_descending(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_available_months

        with app_fixture.app_context():
            result = get_available_months(1)
            for i in range(len(result) - 1):
                curr = result[i]["year"] * 100 + result[i]["month"]
                nxt = result[i + 1]["year"] * 100 + result[i + 1]["month"]
                assert curr >= nxt

    def test_empty_for_different_user(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            _seed_standard_data(1)

        from app.services.monthly_review import get_available_months

        with app_fixture.app_context():
            result = get_available_months(9999)
            assert result == []


class TestGetReviewStep:
    def test_invalid_step_returns_error(self, app_fixture, auth_header, client):
        from app.services.monthly_review import get_review_step

        with app_fixture.app_context():
            result = get_review_step(1, 2026, 3, 0)
            assert "error" in result

            result = get_review_step(1, 2026, 3, 8)
            assert "error" in result


# ── Route Tests ───────────────────────────────────────────────────


class TestReviewRoute:
    def test_get_review(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            _seed_standard_data(1)

        r = client.get("/review/2026/3", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["year"] == 2026
        assert data["month"] == 3
        assert len(data["steps"]) == 7

    def test_invalid_month_zero(self, client, auth_header):
        r = client.get("/review/2026/0", headers=auth_header)
        assert r.status_code == 400

    def test_invalid_month_thirteen(self, client, auth_header):
        r = client.get("/review/2026/13", headers=auth_header)
        assert r.status_code == 400

    def test_unauthorized(self, client):
        r = client.get("/review/2026/3")
        assert r.status_code == 401


class TestReviewStepRoute:
    def test_get_single_step(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            _seed_standard_data(1)

        r = client.get("/review/2026/3/step/1", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["step"] == 1
        assert "Spending Summary" in data["title"]

    def test_invalid_step(self, client, auth_header):
        r = client.get("/review/2026/3/step/0", headers=auth_header)
        assert r.status_code == 400

    def test_each_step_accessible(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            _seed_standard_data(1)

        for step in range(1, 8):
            r = client.get(f"/review/2026/3/step/{step}", headers=auth_header)
            assert r.status_code == 200
            data = r.get_json()
            assert data["step"] == step

    def test_invalid_month(self, client, auth_header):
        r = client.get("/review/2026/13/step/1", headers=auth_header)
        assert r.status_code == 400


class TestAvailableMonthsRoute:
    def test_get_months(self, client, auth_header, app_fixture):
        with app_fixture.app_context():
            _seed_standard_data(1)

        r = client.get("/review/months", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_unauthorized(self, client):
        r = client.get("/review/months")
        assert r.status_code == 401
