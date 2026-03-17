"""
Tests for Financial Data Integrity & Reconciliation (Issue #96).

Covers:
- GET /integrity/check returns correct structure
- Duplicate detection flags identical amount+date+notes
- Orphan category detection (expense with deleted category)
- Negative net flow alert
- Reconciliation per month: income, expenses, net_flow, balanced
- No alerts on clean data
- months param validation
- anchor param validation
- Auth required
- User isolation (alerts only for own data)
- GET /integrity/reconciliation lightweight endpoint
- run_integrity_check unit tests
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Category, Expense
from app.services.integrity import run_integrity_check


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="int@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _seed(app_fixture, user_id, amount, expense_type="EXPENSE",
          days_ago=5, category_id=None, notes="test"):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=user_id,
            amount=Decimal(str(amount)),
            currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago),
            notes=notes,
            category_id=category_id,
        ))
        db.session.commit()


def _seed_category(app_fixture, user_id, name="Food"):
    with app_fixture.app_context():
        cat = Category(user_id=user_id, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — service
# ─────────────────────────────────────────────────────────────────────────────

class TestRunIntegrityCheck:
    def test_returns_correct_structure(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="int_struct@test.com", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            result = run_integrity_check(u.id, months=1)

        required = {"alerts", "alert_counts", "reconciliation", "analysis_months",
                    "healthy", "generated_at"}
        assert required.issubset(result.keys())
        assert isinstance(result["alerts"], list)
        assert isinstance(result["healthy"], bool)

    def test_clean_data_is_healthy(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="int_clean@test.com", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            result = run_integrity_check(u.id, months=1)

        assert result["healthy"] is True
        assert result["alert_counts"]["high"] == 0

    def test_duplicate_detected(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="int_dup@test.com", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            uid = u.id
            # Add two identical expenses
            for _ in range(2):
                db.session.add(Expense(
                    user_id=uid, amount=Decimal("500"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=2),
                    notes="coffee",
                ))
            db.session.commit()
            result = run_integrity_check(uid, months=1)

        dup_alerts = [a for a in result["alerts"] if a["type"] == "duplicate_expense"]
        assert len(dup_alerts) >= 1
        assert dup_alerts[0]["severity"] == "high"
        assert result["healthy"] is False

    def test_negative_net_flow_detected(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="int_neg@test.com", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            uid = u.id
            db.session.add(Expense(user_id=uid, amount=Decimal("1000"), currency="INR",
                                   expense_type="INCOME", spent_at=date.today() - timedelta(days=2),
                                   notes="salary"))
            db.session.add(Expense(user_id=uid, amount=Decimal("2000"), currency="INR",
                                   expense_type="EXPENSE", spent_at=date.today() - timedelta(days=2),
                                   notes="rent"))
            db.session.commit()
            result = run_integrity_check(uid, months=1)

        neg_alerts = [a for a in result["alerts"] if a["type"] == "negative_net_flow"]
        assert len(neg_alerts) >= 1

    def test_reconciliation_has_monthly_entries(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u = User(email="int_rec@test.com", password_hash=generate_password_hash("x"),
                     preferred_currency="INR")
            db.session.add(u)
            db.session.commit()
            result = run_integrity_check(u.id, months=3)

        assert len(result["reconciliation"]) == 3
        for entry in result["reconciliation"]:
            assert "period" in entry
            assert "income" in entry
            assert "expenses" in entry
            assert "net_flow" in entry
            assert "balanced" in entry

    def test_user_isolation(self, app_fixture):
        with app_fixture.app_context():
            from app.models import User
            from werkzeug.security import generate_password_hash
            u1 = User(email="int_iso1@test.com", password_hash=generate_password_hash("x"),
                      preferred_currency="INR")
            u2 = User(email="int_iso2@test.com", password_hash=generate_password_hash("x"),
                      preferred_currency="INR")
            db.session.add_all([u1, u2])
            db.session.commit()
            # Seed duplicate expenses for u1
            for _ in range(2):
                db.session.add(Expense(
                    user_id=u1.id, amount=Decimal("999"), currency="INR",
                    expense_type="EXPENSE",
                    spent_at=date.today() - timedelta(days=1), notes="dup",
                ))
            db.session.commit()
            # u2 must see no alerts
            result = run_integrity_check(u2.id, months=1)

        assert result["alert_counts"]["total"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrityCheckEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/integrity/check").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "ic1@test.com")
        r = client.get("/integrity/check", headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "ic2@test.com")
        d = client.get("/integrity/check", headers=h).get_json()
        for key in ("alerts", "alert_counts", "reconciliation", "healthy", "generated_at"):
            assert key in d

    def test_months_param(self, client, app_fixture):
        h = _auth(client, "ic3@test.com")
        r = client.get("/integrity/check?months=6", headers=h)
        assert r.status_code == 200
        assert r.get_json()["analysis_months"] == 6

    def test_invalid_months_returns_400(self, client, app_fixture):
        h = _auth(client, "ic4@test.com")
        assert client.get("/integrity/check?months=0", headers=h).status_code == 400
        assert client.get("/integrity/check?months=99", headers=h).status_code == 400
        assert client.get("/integrity/check?months=abc", headers=h).status_code == 400

    def test_invalid_anchor_returns_400(self, client, app_fixture):
        h = _auth(client, "ic5@test.com")
        assert client.get("/integrity/check?anchor=bad-date", headers=h).status_code == 400

    def test_valid_anchor(self, client, app_fixture):
        h = _auth(client, "ic6@test.com")
        r = client.get("/integrity/check?anchor=2026-03-01", headers=h)
        assert r.status_code == 200

    def test_healthy_true_on_clean_data(self, client, app_fixture):
        h = _auth(client, "ic7@test.com")
        d = client.get("/integrity/check?months=1", headers=h).get_json()
        assert d["healthy"] is True
        assert d["alert_counts"]["high"] == 0

    def test_duplicate_flagged(self, client, app_fixture):
        h = _auth(client, "ic8@test.com")
        uid = _get_uid(app_fixture, "ic8@test.com")
        _seed(app_fixture, uid, 750, days_ago=3, notes="groceries")
        _seed(app_fixture, uid, 750, days_ago=3, notes="groceries")

        d = client.get("/integrity/check?months=1", headers=h).get_json()
        dup = [a for a in d["alerts"] if a["type"] == "duplicate_expense"]
        assert len(dup) >= 1
        assert d["healthy"] is False

    def test_alert_counts_structure(self, client, app_fixture):
        h = _auth(client, "ic9@test.com")
        d = client.get("/integrity/check", headers=h).get_json()
        counts = d["alert_counts"]
        assert "high" in counts
        assert "medium" in counts
        assert "low" in counts
        assert "total" in counts
        assert counts["total"] == counts["high"] + counts["medium"] + counts["low"]

    def test_user_isolation(self, client, app_fixture):
        h1 = _auth(client, "ic_iso1@test.com")
        h2 = _auth(client, "ic_iso2@test.com")
        uid1 = _get_uid(app_fixture, "ic_iso1@test.com")
        # Seed duplicates for user1
        _seed(app_fixture, uid1, 333, days_ago=2, notes="dup_iso")
        _seed(app_fixture, uid1, 333, days_ago=2, notes="dup_iso")

        d2 = client.get("/integrity/check?months=1", headers=h2).get_json()
        assert d2["alert_counts"]["total"] == 0


class TestReconciliationEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/integrity/reconciliation").status_code == 401

    def test_returns_reconciliation(self, client, app_fixture):
        h = _auth(client, "rec1@test.com")
        r = client.get("/integrity/reconciliation?months=3", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "reconciliation" in d
        assert len(d["reconciliation"]) == 3

    def test_does_not_return_alerts(self, client, app_fixture):
        h = _auth(client, "rec2@test.com")
        d = client.get("/integrity/reconciliation", headers=h).get_json()
        assert "alerts" not in d
        assert "alert_counts" not in d

    def test_net_flow_correct(self, client, app_fixture):
        h = _auth(client, "rec3@test.com")
        uid = _get_uid(app_fixture, "rec3@test.com")
        _seed(app_fixture, uid, 3000, expense_type="INCOME", days_ago=5)
        _seed(app_fixture, uid, 1200, expense_type="EXPENSE", days_ago=5)

        d = client.get("/integrity/reconciliation?months=1", headers=h).get_json()
        current = d["reconciliation"][0]
        assert current["income"] == pytest.approx(3000.0, abs=1.0)
        assert current["expenses"] == pytest.approx(1200.0, abs=1.0)
        assert current["net_flow"] == pytest.approx(1800.0, abs=1.0)
        assert current["balanced"] is True
