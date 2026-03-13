"""Tests for the weekly financial digest feature."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.services.digest import (
    _compute_category_breakdown,
    _compute_daily_spending,
    _detect_anomalies,
    _heuristic_tips,
    _week_bounds,
    generate_digest_email_body,
    generate_weekly_digest,
)


# ---------------------------------------------------------------------------
# Week bounds
# ---------------------------------------------------------------------------

class TestWeekBounds:
    def test_returns_monday_to_sunday(self):
        # Wednesday March 12, 2026
        start, end = _week_bounds(date(2026, 3, 12))
        assert start == date(2026, 3, 9)   # Monday
        assert end == date(2026, 3, 15)     # Sunday
        assert start.weekday() == 0
        assert end.weekday() == 6

    def test_monday_input(self):
        start, end = _week_bounds(date(2026, 3, 9))
        assert start == date(2026, 3, 9)
        assert end == date(2026, 3, 15)

    def test_sunday_input(self):
        start, end = _week_bounds(date(2026, 3, 15))
        assert start == date(2026, 3, 9)
        assert end == date(2026, 3, 15)

    def test_none_returns_previous_week(self):
        # This is date-dependent, just verify it returns valid bounds
        start, end = _week_bounds(None)
        assert start.weekday() == 0
        assert end.weekday() == 6
        assert (end - start).days == 6
        assert end < date.today()


# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------

class TestCategoryBreakdown:
    def test_groups_by_category(self):
        expenses = [
            {"amount": 100, "category_id": 1},
            {"amount": 200, "category_id": 1},
            {"amount": 50, "category_id": 2},
        ]
        cat_map = {1: "Food", 2: "Transport"}
        result = _compute_category_breakdown(expenses, cat_map)
        assert len(result) == 2
        assert result[0]["category"] == "Food"
        assert result[0]["total"] == 300.0
        assert result[0]["count"] == 2
        assert result[1]["category"] == "Transport"
        assert result[1]["total"] == 50.0

    def test_percentages_sum_to_100(self):
        expenses = [
            {"amount": 75, "category_id": 1},
            {"amount": 25, "category_id": 2},
        ]
        cat_map = {1: "A", 2: "B"}
        result = _compute_category_breakdown(expenses, cat_map)
        total_pct = sum(r["pct"] for r in result)
        assert abs(total_pct - 100.0) < 0.1

    def test_uncategorized(self):
        expenses = [{"amount": 50, "category_id": None}]
        result = _compute_category_breakdown(expenses, {})
        assert result[0]["category"] == "Uncategorized"

    def test_empty_expenses(self):
        result = _compute_category_breakdown([], {})
        assert result == []


# ---------------------------------------------------------------------------
# Daily spending
# ---------------------------------------------------------------------------

class TestDailySpending:
    def test_fills_all_seven_days(self):
        start = date(2026, 3, 9)
        end = date(2026, 3, 15)
        expenses = [{"amount": 100, "spent_at": "2026-03-10"}]
        result = _compute_daily_spending(expenses, start, end)
        assert len(result) == 7
        # Tuesday should have 100
        assert result[1]["date"] == "2026-03-10"
        assert result[1]["total"] == 100.0
        # Other days should be 0
        assert result[0]["total"] == 0.0

    def test_multiple_on_same_day(self):
        start = date(2026, 3, 9)
        end = date(2026, 3, 15)
        expenses = [
            {"amount": 50, "spent_at": "2026-03-09"},
            {"amount": 75, "spent_at": "2026-03-09"},
        ]
        result = _compute_daily_spending(expenses, start, end)
        assert result[0]["total"] == 125.0


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

class TestAnomalyDetection:
    def test_spending_spike(self):
        flags = _detect_anomalies(
            expenses=[{"amount": 100, "category_id": 1, "spent_at": "2026-03-10"}],
            cat_map={1: "Food"},
            weekly_total=200,
            prev_week_total=100,
        )
        assert any("jumped" in f.lower() or "100%" in f for f in flags)

    def test_spending_drop(self):
        flags = _detect_anomalies(
            expenses=[{"amount": 50, "category_id": 1, "spent_at": "2026-03-10"}],
            cat_map={1: "Food"},
            weekly_total=50,
            prev_week_total=200,
        )
        assert any("dropped" in f.lower() or "great" in f.lower() for f in flags)

    def test_large_transaction(self):
        flags = _detect_anomalies(
            expenses=[{"amount": 500, "category_id": 1, "spent_at": "2026-03-10"}],
            cat_map={1: "Rent"},
            weekly_total=600,
            prev_week_total=600,
        )
        assert any("large transaction" in f.lower() for f in flags)

    def test_no_expenses_flag(self):
        flags = _detect_anomalies([], {}, 0, 100)
        assert any("no expenses" in f.lower() for f in flags)

    def test_no_anomalies(self):
        flags = _detect_anomalies(
            expenses=[
                {"amount": 30, "category_id": 1, "spent_at": "2026-03-10"},
                {"amount": 35, "category_id": 2, "spent_at": "2026-03-11"},
                {"amount": 35, "category_id": 1, "spent_at": "2026-03-12"},
            ],
            cat_map={1: "Food", 2: "Transport"},
            weekly_total=100,
            prev_week_total=95,
        )
        # Small change, no large txn → no flags
        assert len(flags) == 0


# ---------------------------------------------------------------------------
# Heuristic tips
# ---------------------------------------------------------------------------

class TestHeuristicTips:
    def test_top_category_tip(self):
        breakdown = [{"category": "Food", "total": 500, "pct": 60, "count": 10}]
        tips = _heuristic_tips(breakdown, 500, 400, 0)
        assert any("food" in t.lower() for t in tips)

    def test_overspend_tip(self):
        tips = _heuristic_tips([], 1000, 800, 500)
        assert any("more than you earned" in t.lower() for t in tips)

    def test_saving_tip(self):
        tips = _heuristic_tips([], 300, 300, 1000)
        assert any("saved" in t.lower() for t in tips)

    def test_max_three_tips(self):
        breakdown = [{"category": "X", "total": 100, "pct": 100, "count": 5}]
        tips = _heuristic_tips(breakdown, 1000, 500, 500)
        assert len(tips) <= 3


# ---------------------------------------------------------------------------
# Email body
# ---------------------------------------------------------------------------

class TestEmailBody:
    def test_renders_all_sections(self):
        digest = {
            "week_start": "2026-03-09",
            "week_end": "2026-03-15",
            "total_expenses": 1500.0,
            "total_income": 2000.0,
            "net_flow": 500.0,
            "week_over_week_change_pct": 12.5,
            "transaction_count": 15,
            "category_breakdown": [
                {"category": "Food", "total": 800, "pct": 53.3, "count": 8},
                {"category": "Transport", "total": 700, "pct": 46.7, "count": 7},
            ],
            "anomalies": ["Spending jumped 12% vs last week"],
            "tips": ["Cut food spending by 10%"],
            "upcoming_bills": [
                {"name": "Rent", "amount": 15000, "due_date": "2026-03-20", "autopay": True},
            ],
        }
        body = generate_digest_email_body(digest)
        assert "Weekly Digest" in body
        assert "₹1,500.00" in body
        assert "Food" in body
        assert "jumped" in body
        assert "Cut food" in body
        assert "Rent" in body
        assert "(autopay)" in body
        assert "FinMind" in body


# ---------------------------------------------------------------------------
# Integration: generate_weekly_digest with DB
# ---------------------------------------------------------------------------

class TestGenerateWeeklyDigest:
    def test_empty_week(self, app_fixture):
        """Digest for a user with no data should still return valid structure."""
        with app_fixture.app_context():
            from app.extensions import db
            from app.models import User

            # Create a user
            user = User(
                email="digest@test.com",
                password_hash="hash",
                preferred_currency="INR",
            )
            db.session.add(user)
            db.session.commit()

            digest = generate_weekly_digest(user.id, week_of=date(2026, 3, 12))

            assert digest["total_expenses"] == 0
            assert digest["total_income"] == 0
            assert digest["net_flow"] == 0
            assert digest["transaction_count"] == 0
            assert len(digest["daily_spending"]) == 7
            assert digest["category_breakdown"] == []
            assert digest["method"] == "heuristic"
            assert "tips" in digest

    def test_with_expenses(self, app_fixture):
        """Digest correctly sums expenses and builds breakdown."""
        with app_fixture.app_context():
            from app.extensions import db
            from app.models import Category, Expense, User

            user = User(
                email="digest2@test.com",
                password_hash="hash",
                preferred_currency="INR",
            )
            db.session.add(user)
            db.session.flush()

            cat = Category(user_id=user.id, name="Food")
            db.session.add(cat)
            db.session.flush()

            # Add expenses in week of March 9-15, 2026
            for day_offset, amount in [(0, 100), (1, 200), (3, 150)]:
                db.session.add(Expense(
                    user_id=user.id,
                    category_id=cat.id,
                    amount=amount,
                    spent_at=date(2026, 3, 9) + timedelta(days=day_offset),
                ))
            # Add income
            db.session.add(Expense(
                user_id=user.id,
                amount=1000,
                expense_type="INCOME",
                spent_at=date(2026, 3, 10),
            ))
            db.session.commit()

            digest = generate_weekly_digest(user.id, week_of=date(2026, 3, 12))

            assert digest["total_expenses"] == 450.0
            assert digest["total_income"] == 1000.0
            assert digest["net_flow"] == 550.0
            assert digest["transaction_count"] == 3
            assert len(digest["category_breakdown"]) == 1
            assert digest["category_breakdown"][0]["category"] == "Food"

    def test_week_over_week_change(self, app_fixture):
        """Digest computes WoW change correctly."""
        with app_fixture.app_context():
            from app.extensions import db
            from app.models import Expense, User

            user = User(
                email="digest3@test.com",
                password_hash="hash",
                preferred_currency="INR",
            )
            db.session.add(user)
            db.session.flush()

            # Previous week (March 2-8): 200
            db.session.add(Expense(
                user_id=user.id, amount=200,
                spent_at=date(2026, 3, 4),
            ))
            # Current week (March 9-15): 400
            db.session.add(Expense(
                user_id=user.id, amount=400,
                spent_at=date(2026, 3, 11),
            ))
            db.session.commit()

            digest = generate_weekly_digest(user.id, week_of=date(2026, 3, 12))

            assert digest["total_expenses"] == 400.0
            assert digest["previous_week_expenses"] == 200.0
            assert digest["week_over_week_change_pct"] == 100.0


# ---------------------------------------------------------------------------
# Route integration
# ---------------------------------------------------------------------------

class TestDigestRoutes:
    @patch("app.routes.auth.redis_client")
    def test_weekly_digest_endpoint(self, mock_redis, app_fixture):
        mock_redis.setex = MagicMock()
        mock_redis.get = MagicMock(return_value=None)
        with app_fixture.test_client() as client:
            client.post("/auth/register", json={
                "email": "digestroute@test.com", "password": "pass1234"
            })
            resp = client.post("/auth/login", json={
                "email": "digestroute@test.com", "password": "pass1234"
            })
            token = resp.get_json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.get("/digest/weekly?week_of=2026-03-12", headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert "total_expenses" in data
            assert "daily_spending" in data
            assert "category_breakdown" in data
            assert "tips" in data or "ai_tips" in data

    @patch("app.routes.auth.redis_client")
    def test_email_preview_endpoint(self, mock_redis, app_fixture):
        mock_redis.setex = MagicMock()
        mock_redis.get = MagicMock(return_value=None)
        with app_fixture.test_client() as client:
            client.post("/auth/register", json={
                "email": "digestpreview@test.com", "password": "pass1234"
            })
            resp = client.post("/auth/login", json={
                "email": "digestpreview@test.com", "password": "pass1234"
            })
            token = resp.get_json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}

            resp = client.get(
                "/digest/weekly/email-preview?week_of=2026-03-12",
                headers=headers,
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "email_body" in data
            assert "Weekly Digest" in data["email_body"]
