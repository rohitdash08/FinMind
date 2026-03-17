"""Tests for weekly financial digest endpoint."""
from datetime import date, timedelta
from unittest.mock import patch

from app.extensions import db
from app.models import Expense, Category, Bill, BillCadence


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _add_expense(app_fixture, uid, amount, category_name=None, offset_days=0, expense_type="EXPENSE"):
    with app_fixture.app_context():
        cat_id = None
        if category_name:
            cat = db.session.query(Category).filter_by(user_id=uid, name=category_name).first()
            if not cat:
                cat = Category(user_id=uid, name=category_name)
                db.session.add(cat)
                db.session.flush()
            cat_id = cat.id
        exp = Expense(
            user_id=uid,
            category_id=cat_id,
            amount=amount,
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=offset_days),
        )
        db.session.add(exp)
        db.session.commit()


def _add_bill(app_fixture, uid, name, amount, due_offset_days=3):
    with app_fixture.app_context():
        b = Bill(
            user_id=uid,
            name=name,
            amount=amount,
            currency="INR",
            next_due_date=date.today() + timedelta(days=due_offset_days),
            cadence=BillCadence.MONTHLY,
        )
        db.session.add(b)
        db.session.commit()


def _get_uid(client):
    r = client.post("/auth/register", json={"email": "digest@test.com", "password": "pass1234"})
    r = client.post("/auth/login", json={"email": "digest@test.com", "password": "pass1234"})
    return r.get_json()["access_token"] if r.status_code == 200 else None


class TestWeeklyDigest:
    def test_empty_week_returns_zero_summary(self, client, auth_header, app_fixture):
        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_spent"] == 0.0
        assert data["summary"]["total_income"] == 0.0
        assert data["category_breakdown"] == []
        assert "week_start" in data
        assert "week_end" in data
        assert "insights" in data

    def test_expenses_appear_in_breakdown(self, client, auth_header, app_fixture):
        uid = 1
        _add_expense(app_fixture, uid, 500, "Food", offset_days=1)
        _add_expense(app_fixture, uid, 200, "Transport", offset_days=2)

        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["summary"]["total_spent"] == 700.0
        cats = {c["category"]: c["total"] for c in data["category_breakdown"]}
        assert cats["Food"] == 500.0
        assert cats["Transport"] == 200.0

    def test_income_excluded_from_spending(self, client, auth_header, app_fixture):
        uid = 1
        _add_expense(app_fixture, uid, 1000, offset_days=1, expense_type="INCOME")
        _add_expense(app_fixture, uid, 300, "Bills", offset_days=1)

        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["total_spent"] == 300.0
        assert data["summary"]["total_income"] == 1000.0
        assert data["summary"]["net_flow"] == 700.0

    def test_custom_week_start(self, client, auth_header, app_fixture):
        week_start = (date.today() - timedelta(days=14)).isoformat()
        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get(f"/digest/weekly?week_start={week_start}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["week_start"] == week_start

    def test_upcoming_bills_included(self, client, auth_header, app_fixture):
        uid = 1
        _add_bill(app_fixture, uid, "Netflix", 500, due_offset_days=3)

        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        bill_names = [b["name"] for b in data["upcoming_bills"]]
        assert "Netflix" in bill_names

    def test_top_spending_category_is_highest(self, client, auth_header, app_fixture):
        uid = 1
        _add_expense(app_fixture, uid, 100, "Food", offset_days=1)
        _add_expense(app_fixture, uid, 800, "Rent", offset_days=2)

        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        assert r.get_json()["top_spending_category"] == "Rent"

    def test_wow_change_computed(self, client, auth_header, app_fixture):
        uid = 1
        # Current week: 500
        _add_expense(app_fixture, uid, 500, "Food", offset_days=1)
        # Previous week: 250
        _add_expense(app_fixture, uid, 250, "Food", offset_days=8)

        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        data = r.get_json()
        assert data["summary"]["prev_week_spent"] == 250.0
        assert data["summary"]["wow_change_pct"] == 100.0

    def test_cache_hit_returns_cached(self, client, auth_header):
        cached = {"week_start": "2026-03-09", "cached": True}
        with patch("app.routes.digest.cache_get", return_value=cached):
            r = client.get("/digest/weekly", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json().get("cached") is True

    def test_requires_auth(self, client):
        r = client.get("/digest/weekly")
        assert r.status_code == 401

    def test_insights_not_empty(self, client, auth_header, app_fixture):
        uid = 1
        _add_expense(app_fixture, uid, 400, "Food", offset_days=1)
        with patch("app.routes.digest.cache_get", return_value=None), \
             patch("app.routes.digest.cache_set"):
            r = client.get("/digest/weekly", headers=auth_header)
        assert len(r.get_json()["insights"]) > 0
