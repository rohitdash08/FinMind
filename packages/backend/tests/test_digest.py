"""Tests for weekly digest feature."""

from datetime import date, timedelta

from app.extensions import db
from app.models import Expense, Category
from app.services.digest import (
    _week_boundaries,
    _build_digest_data,
    _heuristic_summary,
)


class TestWeekBoundaries:
    def test_returns_monday_to_sunday(self):
        # Wednesday 2026-03-18
        start, end = _week_boundaries(date(2026, 3, 18))
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday
        assert start == date(2026, 3, 9)
        assert end == date(2026, 3, 15)

    def test_monday_returns_previous_week(self):
        start, end = _week_boundaries(date(2026, 3, 16))  # Monday
        assert start == date(2026, 3, 9)
        assert end == date(2026, 3, 15)

    def test_sunday_returns_previous_week(self):
        # On Sunday, the "previous completed week" is the week before
        start, end = _week_boundaries(date(2026, 3, 22))  # Sunday
        assert start == date(2026, 3, 9)
        assert end == date(2026, 3, 15)


class TestBuildDigestData:
    def test_empty_week(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            data = _build_digest_data(1, date(2026, 1, 5), date(2026, 1, 11))
            assert data["total_spent"] == 0
            assert data["transaction_count"] == 0

    def test_with_expenses(self, app_fixture, auth_header, client):
        with app_fixture.app_context():
            cat = Category(user_id=1, name="Food")
            db.session.add(cat)
            db.session.flush()

            for i in range(3):
                db.session.add(
                    Expense(
                        user_id=1,
                        category_id=cat.id,
                        amount=100 + i * 10,
                        spent_at=date(2026, 3, 10 + i),
                    )
                )
            db.session.commit()

            data = _build_digest_data(1, date(2026, 3, 9), date(2026, 3, 15))
            assert data["total_spent"] == 330.0
            assert data["transaction_count"] == 3
            assert len(data["top_categories"]) == 1
            assert data["top_categories"][0]["category"] == "Food"


class TestHeuristicSummary:
    def test_positive_net_flow(self):
        data = {
            "week_start": "2026-03-09",
            "week_end": "2026-03-15",
            "total_spent": 500,
            "total_income": 1000,
            "net_flow": 500,
            "week_over_week_change_pct": -10,
            "previous_week_spent": 555,
            "top_categories": [{"category": "Food", "total": 300, "count": 5}],
            "transaction_count": 5,
        }
        result = _heuristic_summary(data)
        assert "summary" in result
        assert "tips" in result
        assert result["method"] == "heuristic"
        assert "decreased" in result["summary"]

    def test_negative_net_flow_warns(self):
        data = {
            "week_start": "2026-03-09",
            "week_end": "2026-03-15",
            "total_spent": 1500,
            "total_income": 1000,
            "net_flow": -500,
            "week_over_week_change_pct": 25,
            "previous_week_spent": 1200,
            "top_categories": [],
            "transaction_count": 10,
        }
        result = _heuristic_summary(data)
        assert any("exceeded" in t for t in result["tips"])
        assert any("jumped" in t for t in result["tips"])


class TestDigestEndpoints:
    def test_latest_empty(self, client, auth_header):
        r = client.get("/digest/latest", headers=auth_header)
        assert r.status_code == 404

    def test_history_empty(self, client, auth_header):
        r = client.get("/digest/history", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_generate_no_transactions(self, client, auth_header):
        r = client.post("/digest/generate", headers=auth_header)
        assert r.status_code == 404

    def test_full_flow(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            # Add expenses for last week
            start, end = _week_boundaries()
            for i in range(5):
                day = start + timedelta(days=i)
                db.session.add(
                    Expense(
                        user_id=1,
                        amount=50 + i * 10,
                        spent_at=day,
                    )
                )
            db.session.commit()

        # Generate digest
        r = client.post("/digest/generate", headers=auth_header)
        assert r.status_code == 201
        data = r.get_json()
        assert "summary" in data
        assert data["method"] == "heuristic"

        # Get latest
        r = client.get("/digest/latest", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["id"] == data["id"]

        # Get history
        r = client.get("/digest/history", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 1

    def test_idempotent_generation(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            start, _ = _week_boundaries()
            db.session.add(Expense(user_id=1, amount=100, spent_at=start))
            db.session.commit()

        r1 = client.post("/digest/generate", headers=auth_header)
        r2 = client.post("/digest/generate", headers=auth_header)
        assert r1.status_code == 201
        # Second call returns the same digest (idempotent)
        assert r2.status_code == 201
        assert r1.get_json()["id"] == r2.get_json()["id"]

    def test_history_limit(self, client, auth_header):
        r = client.get("/digest/history?limit=5", headers=auth_header)
        assert r.status_code == 200
