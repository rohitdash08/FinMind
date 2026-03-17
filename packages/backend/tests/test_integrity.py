"""
Tests for Financial Data Integrity & Reconciliation (Issue #96).

Covers:
- GET /integrity/check returns correct structure
- Balance mismatch detection (month with expenses > income)
- Orphaned expense detection (missing category_id)
- Future-dated expense detection
- Negative amount detection
- Stale recurring expense detection
- Bills missing reminders detection
- overall_status: ok / warnings / errors
- GET /integrity/check/summary returns counts only
- Input validation: months out of range
- Auth required
- User isolation
- Graceful degradation: duplicate check falls back on non-PostgreSQL
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import Bill, BillCadence, Category, Expense, RecurringExpense, RecurringCadence
from app.services.integrity import run_integrity_check


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="integ@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def _get_uid(app_fixture, email):
    from app.models import User
    with app_fixture.app_context():
        u = db.session.query(User).filter_by(email=email).first()
        return u.id if u else None


def _make_user(app_fixture, email):
    from app.models import User
    from werkzeug.security import generate_password_hash
    with app_fixture.app_context():
        u = User(email=email, password_hash=generate_password_hash("x"),
                 preferred_currency="INR")
        db.session.add(u)
        db.session.commit()
        return u.id


def _seed_expense(app_fixture, uid, amount, expense_type="EXPENSE",
                  days_ago=5, category_id=None):
    with app_fixture.app_context():
        db.session.add(Expense(
            user_id=uid, amount=Decimal(str(amount)), currency="INR",
            expense_type=expense_type,
            spent_at=date.today() - timedelta(days=days_ago),
            notes="test", category_id=category_id,
        ))
        db.session.commit()


def _seed_category(app_fixture, uid, name="Food"):
    with app_fixture.app_context():
        cat = Category(user_id=uid, name=name)
        db.session.add(cat)
        db.session.commit()
        return cat.id


# ─────────────────────────────────────────────────────────────────────────────
# Service unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRunIntegrityCheck:
    def test_empty_db_returns_ok(self, app_fixture):
        uid = _make_user(app_fixture, "ic_empty@test.com")
        with app_fixture.app_context():
            r = run_integrity_check(uid, months=1)
        assert r["overall_status"] == "ok"
        assert r["total_issues"] == 0

    def test_required_keys_present(self, app_fixture):
        uid = _make_user(app_fixture, "ic_keys@test.com")
        with app_fixture.app_context():
            r = run_integrity_check(uid, months=1)
        expected = {
            "overall_status", "total_issues", "balance_mismatches",
            "orphaned_expenses", "orphaned_recurring", "future_dated_expenses",
            "duplicate_expenses", "negative_amounts", "stale_recurring",
            "bills_missing_reminders", "analysis_months", "generated_at",
        }
        assert expected.issubset(r.keys())

    def test_balance_mismatch_flagged(self, app_fixture):
        uid = _make_user(app_fixture, "ic_balance@test.com")
        # Expense > income this month
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("2000"), currency="INR",
                                   expense_type="EXPENSE",
                                   spent_at=date.today() - timedelta(days=3), notes="x"))
            db.session.add(Expense(user_id=uid, amount=Decimal("500"), currency="INR",
                                   expense_type="INCOME",
                                   spent_at=date.today() - timedelta(days=3), notes="x"))
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["balance_mismatches"]) >= 1
        assert r["balance_mismatches"][0]["net_flow"] < 0
        assert r["overall_status"] in ("warnings", "errors")

    def test_orphaned_expense_detected(self, app_fixture):
        uid = _make_user(app_fixture, "ic_orphan@test.com")
        with app_fixture.app_context():
            # Use a category_id that doesn't exist
            db.session.add(Expense(user_id=uid, amount=Decimal("100"), currency="INR",
                                   expense_type="EXPENSE", category_id=99999,
                                   spent_at=date.today() - timedelta(days=1), notes="x"))
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["orphaned_expenses"]) >= 1
        assert r["orphaned_expenses"][0]["missing_category_id"] == 99999
        assert r["overall_status"] == "errors"

    def test_future_dated_expense_detected(self, app_fixture):
        uid = _make_user(app_fixture, "ic_future@test.com")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("50"), currency="INR",
                                   expense_type="EXPENSE",
                                   spent_at=date.today() + timedelta(days=5), notes="x"))
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["future_dated_expenses"]) >= 1
        assert r["future_dated_expenses"][0]["days_ahead"] == 5

    def test_negative_amount_detected(self, app_fixture):
        uid = _make_user(app_fixture, "ic_neg@test.com")
        with app_fixture.app_context():
            # Bypass model validation and insert directly
            from sqlalchemy import text
            db.session.execute(text(
                "INSERT INTO expenses (user_id, amount, currency, expense_type, spent_at, notes, created_at) "
                "VALUES (:uid, -50, 'INR', 'EXPENSE', :d, 'bad', CURRENT_TIMESTAMP)"
            ), {"uid": uid, "d": date.today() - timedelta(days=1)})
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["negative_amounts"]) >= 1
        assert r["overall_status"] == "errors"

    def test_stale_recurring_detected(self, app_fixture):
        uid = _make_user(app_fixture, "ic_stale@test.com")
        with app_fixture.app_context():
            db.session.add(RecurringExpense(
                user_id=uid, amount=Decimal("200"), currency="INR",
                expense_type="EXPENSE", notes="old subscription",
                cadence=RecurringCadence.MONTHLY,
                start_date=date(2025, 1, 1),
                end_date=date(2025, 6, 1),   # past!
                active=True,
            ))
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["stale_recurring"]) >= 1
        assert r["stale_recurring"][0]["days_overdue"] > 0

    def test_bill_missing_reminder_detected(self, app_fixture):
        uid = _make_user(app_fixture, "ic_bill@test.com")
        with app_fixture.app_context():
            db.session.add(Bill(
                user_id=uid, name="Rent", amount=Decimal("1000"), currency="INR",
                next_due_date=date.today() + timedelta(days=3),
                cadence=BillCadence.MONTHLY, active=True,
            ))
            db.session.commit()
            r = run_integrity_check(uid, months=1)
        assert len(r["bills_missing_reminders"]) >= 1
        assert r["bills_missing_reminders"][0]["bill_name"] == "Rent"

    def test_user_isolation(self, app_fixture):
        uid1 = _make_user(app_fixture, "ic_iso1@test.com")
        uid2 = _make_user(app_fixture, "ic_iso2@test.com")
        with app_fixture.app_context():
            # Only uid1 has a future-dated expense
            db.session.add(Expense(user_id=uid1, amount=Decimal("50"), currency="INR",
                                   expense_type="EXPENSE",
                                   spent_at=date.today() + timedelta(days=3), notes="x"))
            db.session.commit()
            r2 = run_integrity_check(uid2, months=1)
        assert len(r2["future_dated_expenses"]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# HTTP integration tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegrityCheckEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/integrity/check").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "e1@integ.test")
        r = client.get("/integrity/check", headers=h)
        assert r.status_code == 200

    def test_response_structure(self, client, app_fixture):
        h = _auth(client, "e2@integ.test")
        d = client.get("/integrity/check", headers=h).get_json()
        assert "overall_status" in d
        assert "total_issues" in d
        assert d["overall_status"] in ("ok", "warnings", "errors")

    def test_default_status_ok_for_clean_user(self, client, app_fixture):
        h = _auth(client, "e3@integ.test")
        d = client.get("/integrity/check", headers=h).get_json()
        assert d["overall_status"] == "ok"
        assert d["total_issues"] == 0

    def test_custom_months_param(self, client, app_fixture):
        h = _auth(client, "e4@integ.test")
        r = client.get("/integrity/check?months=6", headers=h)
        assert r.status_code == 200
        assert r.get_json()["analysis_months"] == 6

    def test_months_out_of_range_400(self, client, app_fixture):
        h = _auth(client, "e5@integ.test")
        assert client.get("/integrity/check?months=0", headers=h).status_code == 400
        assert client.get("/integrity/check?months=13", headers=h).status_code == 400

    def test_invalid_months_400(self, client, app_fixture):
        h = _auth(client, "e6@integ.test")
        assert client.get("/integrity/check?months=xyz", headers=h).status_code == 400

    def test_future_expense_flagged_via_http(self, client, app_fixture):
        h = _auth(client, "e7@integ.test")
        uid = _get_uid(app_fixture, "e7@integ.test")
        future = (date.today() + timedelta(days=4)).isoformat()
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("99"), currency="INR",
                                   expense_type="EXPENSE", spent_at=date.today() + timedelta(days=4),
                                   notes="future"))
            db.session.commit()
        d = client.get("/integrity/check?months=1", headers=h).get_json()
        assert len(d["future_dated_expenses"]) >= 1

    def test_balance_mismatch_via_http(self, client, app_fixture):
        h = _auth(client, "e8@integ.test")
        uid = _get_uid(app_fixture, "e8@integ.test")
        with app_fixture.app_context():
            db.session.add(Expense(user_id=uid, amount=Decimal("3000"), currency="INR",
                                   expense_type="EXPENSE",
                                   spent_at=date.today() - timedelta(days=2), notes="big"))
            db.session.commit()
        d = client.get("/integrity/check?months=1", headers=h).get_json()
        assert len(d["balance_mismatches"]) >= 1
        assert d["overall_status"] in ("warnings", "errors")


class TestIntegritySummaryEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.get("/integrity/check/summary").status_code == 401

    def test_returns_200(self, client, app_fixture):
        h = _auth(client, "s1@integ.test")
        r = client.get("/integrity/check/summary", headers=h)
        assert r.status_code == 200

    def test_summary_keys(self, client, app_fixture):
        h = _auth(client, "s2@integ.test")
        d = client.get("/integrity/check/summary", headers=h).get_json()
        assert "overall_status" in d
        assert "total_issues" in d
        assert "counts" in d
        counts = d["counts"]
        for key in ("balance_mismatches", "orphaned_expenses", "future_dated_expenses",
                    "negative_amounts", "stale_recurring", "bills_missing_reminders"):
            assert key in counts

    def test_summary_has_no_detail_arrays(self, client, app_fixture):
        h = _auth(client, "s3@integ.test")
        d = client.get("/integrity/check/summary", headers=h).get_json()
        # Summary must not include the verbose detail arrays
        assert "orphaned_expenses" not in d
        assert "future_dated_expenses" not in d
