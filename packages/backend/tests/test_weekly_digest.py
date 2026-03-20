"""Tests for the weekly financial digest feature (issue #121).

Covers the ``GET /digest/weekly`` endpoint and the underlying
``weekly_digest`` service with various data scenarios.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import Category, Expense


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday() + 7)


def _seed_expenses(app, uid, monday):
    """Insert realistic expenses across the target week."""
    with app.app_context():
        # Create categories
        cat_food = Category(user_id=uid, name="Food")
        cat_transport = Category(user_id=uid, name="Transport")
        cat_entertainment = Category(user_id=uid, name="Entertainment")
        db.session.add_all([cat_food, cat_transport, cat_entertainment])
        db.session.flush()

        expenses = [
            # Monday - Food
            Expense(
                user_id=uid, category_id=cat_food.id, amount=25.50,
                expense_type="EXPENSE", spent_at=monday, notes="Lunch",
            ),
            # Tuesday - Transport
            Expense(
                user_id=uid, category_id=cat_transport.id, amount=15.00,
                expense_type="EXPENSE", spent_at=monday + timedelta(days=1),
                notes="Bus pass",
            ),
            # Wednesday - Food + Entertainment
            Expense(
                user_id=uid, category_id=cat_food.id, amount=42.00,
                expense_type="EXPENSE", spent_at=monday + timedelta(days=2),
                notes="Dinner out",
            ),
            Expense(
                user_id=uid, category_id=cat_entertainment.id, amount=18.99,
                expense_type="EXPENSE", spent_at=monday + timedelta(days=2),
                notes="Movie tickets",
            ),
            # Thursday - Income
            Expense(
                user_id=uid, category_id=None, amount=500.00,
                expense_type="INCOME", spent_at=monday + timedelta(days=3),
                notes="Freelance payment",
            ),
            # Friday - Food
            Expense(
                user_id=uid, category_id=cat_food.id, amount=33.75,
                expense_type="EXPENSE", spent_at=monday + timedelta(days=4),
                notes="Groceries",
            ),
            # Saturday - Transport
            Expense(
                user_id=uid, category_id=cat_transport.id, amount=22.00,
                expense_type="EXPENSE", spent_at=monday + timedelta(days=5),
                notes="Ride share",
            ),
        ]
        db.session.add_all(expenses)
        db.session.commit()
        return {
            "food_id": cat_food.id,
            "transport_id": cat_transport.id,
            "entertainment_id": cat_entertainment.id,
        }


def _seed_previous_week(app, uid, monday):
    """Insert expenses for the week before *monday* to test WoW comparison."""
    prev_monday = monday - timedelta(days=7)
    with app.app_context():
        cat = Category.query.filter_by(user_id=uid, name="Food").first()
        cat_id = cat.id if cat else None
        expenses = [
            Expense(
                user_id=uid, category_id=cat_id, amount=80.00,
                expense_type="EXPENSE", spent_at=prev_monday,
                notes="Prev week food",
            ),
            Expense(
                user_id=uid, category_id=cat_id, amount=60.00,
                expense_type="EXPENSE",
                spent_at=prev_monday + timedelta(days=3),
                notes="Prev week groceries",
            ),
        ]
        db.session.add_all(expenses)
        db.session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWeeklyDigestEndpoint:
    """Integration tests for GET /digest/weekly."""

    def test_digest_requires_auth(self, client):
        """Unauthenticated requests are rejected."""
        resp = client.get("/digest/weekly")
        assert resp.status_code in (401, 422)

    def test_digest_empty_week(self, client, auth_header):
        """Digest for a week with no data returns zero totals."""
        resp = client.get(
            "/digest/weekly?week=2020-01-06", headers=auth_header
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_spending"] == 0
        assert data["total_income"] == 0
        assert data["net_flow"] == 0
        assert data["transaction_count"] == 0
        assert data["week_over_week_change_pct"] == 0
        assert data["category_breakdown"] == []
        assert isinstance(data["insights"], list)
        assert data["method"] == "heuristic"

    def test_digest_with_data(self, app_fixture, client, auth_header):
        """Digest correctly aggregates seeded expenses."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.get_json()

        # Total spending = 25.50 + 15.00 + 42.00 + 18.99 + 33.75 + 22.00 = 157.24
        assert data["total_spending"] == pytest.approx(157.24, abs=0.01)
        assert data["total_income"] == pytest.approx(500.00, abs=0.01)
        assert data["net_flow"] == pytest.approx(342.76, abs=0.01)
        assert data["transaction_count"] == 6

        # Category breakdown present and sorted descending
        cats = data["category_breakdown"]
        assert len(cats) == 3
        assert cats[0]["amount"] >= cats[1]["amount"] >= cats[2]["amount"]

        # Percentages sum to ~100
        pct_sum = sum(c["percentage"] for c in cats)
        assert pct_sum == pytest.approx(100.0, abs=1.0)

    def test_digest_wow_comparison(self, app_fixture, client, auth_header):
        """Week-over-week percentage reflects previous week data."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)
        _seed_previous_week(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.get_json()

        # prev = 140, current = 157.24 => wow ~+12.31%
        assert data["previous_week_spending"] == pytest.approx(140.0, abs=0.01)
        assert data["week_over_week_change_pct"] == pytest.approx(12.31, abs=0.5)

    def test_digest_daily_breakdown(self, app_fixture, client, auth_header):
        """Daily breakdown returns entries for days with transactions."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers=auth_header,
        )
        data = resp.get_json()
        daily = data["daily_breakdown"]
        assert len(daily) >= 1
        for entry in daily:
            assert "date" in entry
            assert "amount" in entry
            assert "transaction_count" in entry

    def test_digest_invalid_week_format(self, client, auth_header):
        """Bad week param returns 400."""
        resp = client.get(
            "/digest/weekly?week=not-a-date", headers=auth_header
        )
        assert resp.status_code == 400
        assert "error" in resp.get_json()

    def test_digest_currency_param(self, app_fixture, client, auth_header):
        """Currency param is echoed back in response."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}&currency=USD",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("currency") == "USD"

    def test_digest_default_week(self, app_fixture, client, auth_header):
        """Omitting week param still returns a valid digest."""
        resp = client.get("/digest/weekly", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "week_start" in data
        assert "week_end" in data
        assert "total_spending" in data

    def test_digest_insights_non_empty_with_data(
        self, app_fixture, client, auth_header
    ):
        """When data exists, insights list is populated."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers=auth_header,
        )
        data = resp.get_json()
        assert len(data["insights"]) >= 1

    @patch(
        "app.services.weekly_digest._gemini_narrative",
        return_value="Great week! You saved more than usual.",
    )
    def test_digest_gemini_narrative(
        self, mock_gemini, app_fixture, client, auth_header
    ):
        """When Gemini key is provided and succeeds, narrative is included."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers={
                **auth_header,
                "X-Gemini-Api-Key": "test-key-123",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["method"] == "gemini"
        assert "narrative" in data
        assert "Great week" in data["narrative"]
        mock_gemini.assert_called_once()

    @patch(
        "app.services.weekly_digest._gemini_narrative",
        side_effect=Exception("API timeout"),
    )
    def test_digest_gemini_fallback(
        self, mock_gemini, app_fixture, client, auth_header
    ):
        """When Gemini fails, digest falls back to heuristic gracefully."""
        monday = _last_monday()
        _seed_expenses(app_fixture, 1, monday)

        resp = client.get(
            f"/digest/weekly?week={monday.isoformat()}",
            headers={
                **auth_header,
                "X-Gemini-Api-Key": "test-key-123",
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["method"] == "heuristic"
        assert "gemini_unavailable" in data.get("warnings", [])
        assert "narrative" not in data

    def test_digest_week_bounds_snap_to_monday(
        self, app_fixture, client, auth_header
    ):
        """Passing a Wednesday still returns the full Mon-Sun range."""
        monday = _last_monday()
        wednesday = monday + timedelta(days=2)

        resp = client.get(
            f"/digest/weekly?week={wednesday.isoformat()}",
            headers=auth_header,
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["week_start"] == monday.isoformat()
        assert data["week_end"] == (monday + timedelta(days=6)).isoformat()
