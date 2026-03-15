"""Tests for spending trend heatmap visualization."""

import pytest
from datetime import datetime, timedelta, date
from app.extensions import db
from app.models import Expense, Category


def _create_category(client, name="Food"):
    with client.application.app_context():
        cat = Category(name=name, user_id=1)
        db.session.add(cat)
        db.session.commit()
        return cat.id


def _create_expense(client, user_id=1, amount=100, category_id=None, days_ago=0):
    with client.application.app_context():
        exp = Expense(
            user_id=user_id,
            notes="Test",
            amount=amount,
            category_id=category_id,
            spent_at=date.today() - timedelta(days=days_ago),
        )
        db.session.add(exp)
        db.session.commit()
        return exp.id


# ═══════════════════════════════════════════════════════════════════
# Service unit tests
# ═══════════════════════════════════════════════════════════════════


class TestDailyHeatmap:
    def test_empty(self, client, auth_header):
        from app.services.spending_heatmap import get_daily_heatmap

        with client.application.app_context():
            result = get_daily_heatmap(1, days=30)

        assert len(result["days"]) == 30
        assert result["active_days"] == 0
        assert result["total_spending"] == 0

    def test_with_data(self, client, auth_header):
        from app.services.spending_heatmap import get_daily_heatmap

        _create_expense(client, amount=100, days_ago=5)
        _create_expense(client, amount=50, days_ago=5)
        _create_expense(client, amount=200, days_ago=10)

        with client.application.app_context():
            result = get_daily_heatmap(1, days=30)

        assert result["active_days"] == 2
        assert result["total_spending"] == 350
        assert result["max_daily_amount"] == 200  # Day with $200

    def test_intensity_calculation(self, client, auth_header):
        from app.services.spending_heatmap import get_daily_heatmap

        _create_expense(client, amount=100, days_ago=5)
        _create_expense(client, amount=50, days_ago=10)

        with client.application.app_context():
            result = get_daily_heatmap(1, days=30)

        active = [d for d in result["days"] if d["amount"] > 0]
        max_day = max(active, key=lambda d: d["amount"])
        assert max_day["intensity"] == 1.0  # Max day has intensity 1.0

    def test_filter_by_category(self, client, auth_header):
        from app.services.spending_heatmap import get_daily_heatmap

        cat1 = _create_category(client, "Food")
        cat2 = _create_category(client, "Transport")
        _create_expense(client, amount=100, category_id=cat1, days_ago=5)
        _create_expense(client, amount=200, category_id=cat2, days_ago=5)

        with client.application.app_context():
            result = get_daily_heatmap(1, days=30, category_id=cat1)

        assert result["total_spending"] == 100

    def test_day_of_week(self, client, auth_header):
        from app.services.spending_heatmap import get_daily_heatmap

        with client.application.app_context():
            result = get_daily_heatmap(1, days=7)

        assert all("day_of_week" in d for d in result["days"])
        assert all(0 <= d["day_of_week"] <= 6 for d in result["days"])


class TestWeeklyHeatmap:
    def test_empty(self, client, auth_header):
        from app.services.spending_heatmap import get_weekly_heatmap

        with client.application.app_context():
            result = get_weekly_heatmap(1, weeks=4)

        assert result["total_spending"] == 0

    def test_with_data(self, client, auth_header):
        from app.services.spending_heatmap import get_weekly_heatmap

        _create_expense(client, amount=100, days_ago=3)
        _create_expense(client, amount=200, days_ago=10)

        with client.application.app_context():
            result = get_weekly_heatmap(1, weeks=4)

        assert result["total_spending"] == 300


class TestHourlyHeatmap:
    def test_empty(self, client, auth_header):
        from app.services.spending_heatmap import get_hourly_heatmap

        with client.application.app_context():
            result = get_hourly_heatmap(1, days=30)

        assert len(result["cells"]) == 168  # 7 * 24
        assert result["max_amount"] == 0

    def test_with_data(self, client, auth_header):
        from app.services.spending_heatmap import get_hourly_heatmap

        _create_expense(client, amount=100, days_ago=3)

        with client.application.app_context():
            result = get_hourly_heatmap(1, days=30)

        assert result["max_amount"] > 0
        assert any(c["amount"] > 0 for c in result["cells"])


class TestCategoryHeatmap:
    def test_empty(self, client, auth_header):
        from app.services.spending_heatmap import get_category_heatmap

        with client.application.app_context():
            result = get_category_heatmap(1, days=30)

        assert result["categories"] == []

    def test_with_data(self, client, auth_header):
        from app.services.spending_heatmap import get_category_heatmap

        cat1 = _create_category(client, "Food")
        cat2 = _create_category(client, "Transport")
        _create_expense(client, amount=200, category_id=cat1, days_ago=5)
        _create_expense(client, amount=100, category_id=cat2, days_ago=5)

        with client.application.app_context():
            result = get_category_heatmap(1, days=30)

        assert result["total_categories"] == 2
        # Sorted by amount descending
        assert result["categories"][0]["amount"] > result["categories"][1]["amount"]

    def test_uncategorized(self, client, auth_header):
        from app.services.spending_heatmap import get_category_heatmap

        _create_expense(client, amount=50, days_ago=3)  # No category

        with client.application.app_context():
            result = get_category_heatmap(1, days=30)

        assert result["total_categories"] == 1
        assert result["categories"][0]["category_name"] == "Uncategorized"


class TestHeatmapSummary:
    def test_empty(self, client, auth_header):
        from app.services.spending_heatmap import get_heatmap_summary

        with client.application.app_context():
            result = get_heatmap_summary(1, days=30)

        assert result["total_spending"] == 0
        assert result["active_days"] == 0
        assert result["activity_rate"] == 0

    def test_with_data(self, client, auth_header):
        from app.services.spending_heatmap import get_heatmap_summary

        _create_expense(client, amount=100, days_ago=3)
        _create_expense(client, amount=200, days_ago=5)
        _create_expense(client, amount=50, days_ago=5)

        with client.application.app_context():
            result = get_heatmap_summary(1, days=30)

        assert result["total_spending"] == 350
        assert result["total_transactions"] == 3
        assert result["active_days"] == 2
        assert result["max_single_transaction"] == 200
        assert result["busiest_day_amount"] == 250  # $200 + $50 on same day


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestHeatmapRoutes:
    # ── GET /heatmap/daily ──
    def test_daily_route(self, client, auth_header):
        r = client.get("/heatmap/daily", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "days" in body
        assert "total_spending" in body

    def test_daily_with_params(self, client, auth_header):
        r = client.get("/heatmap/daily?days=30", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total_days"] == 30

    def test_daily_unauthorized(self, client):
        r = client.get("/heatmap/daily")
        assert r.status_code == 401

    # ── GET /heatmap/weekly ──
    def test_weekly_route(self, client, auth_header):
        r = client.get("/heatmap/weekly", headers=auth_header)
        assert r.status_code == 200
        assert "weeks" in r.get_json()

    def test_weekly_with_params(self, client, auth_header):
        r = client.get("/heatmap/weekly?weeks=12", headers=auth_header)
        assert r.status_code == 200

    # ── GET /heatmap/hourly ──
    def test_hourly_route(self, client, auth_header):
        r = client.get("/heatmap/hourly", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "cells" in body
        assert len(body["cells"]) == 168

    # ── GET /heatmap/categories ──
    def test_categories_route(self, client, auth_header):
        r = client.get("/heatmap/categories", headers=auth_header)
        assert r.status_code == 200
        assert "categories" in r.get_json()

    # ── GET /heatmap/summary ──
    def test_summary_route(self, client, auth_header):
        r = client.get("/heatmap/summary", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "total_spending" in body
        assert "activity_rate" in body

    def test_summary_with_days(self, client, auth_header):
        r = client.get("/heatmap/summary?days=30", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["total_days"] == 30
