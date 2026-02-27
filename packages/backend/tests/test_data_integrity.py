"""Tests for financial data integrity & reconciliation."""

import pytest
from datetime import date, timedelta
from app.services.data_integrity import (
    run_all_checks, run_check, reconcile, get_history,
    get_reconciliations, CHECK_TYPES,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def expenses(app, user):
    with app.app_context():
        from app.extensions import db
        from app.models import Expense, Category
        cat = Category(name="Food", user_id=user)
        db.session.add(cat)
        db.session.flush()
        for i in range(5):
            e = Expense(
                user_id=user, amount=10.0 * (i + 1),
                description=f"Expense {i}", date=date.today(),
                category_id=cat.id,
            )
            db.session.add(e)
        db.session.commit()
        return user


class TestChecks:
    def test_run_all(self, app, expenses):
        with app.app_context():
            results = run_all_checks(expenses)
            assert len(results) == len(CHECK_TYPES)
            assert all(r["status"] in ("pass", "warn", "fail") for r in results)

    def test_orphans_pass(self, app, expenses):
        with app.app_context():
            r = run_check(expenses, "orphan_expenses")
            assert r["status"] == "pass"

    def test_orphans_warn(self, app, user):
        with app.app_context():
            from app.extensions import db
            from app.models import Expense
            e = Expense(user_id=user, amount=10, description="No cat", date=date.today())
            db.session.add(e)
            db.session.commit()
            r = run_check(user, "orphan_expenses")
            assert r["status"] == "warn"
            assert r["details"]["orphan_count"] == 1

    def test_duplicates_pass(self, app, expenses):
        with app.app_context():
            r = run_check(expenses, "duplicate_expenses")
            assert r["status"] == "pass"

    def test_duplicates_warn(self, app, user):
        with app.app_context():
            from app.extensions import db
            from app.models import Expense
            for _ in range(2):
                e = Expense(user_id=user, amount=50, description="Same", date=date.today())
                db.session.add(e)
            db.session.commit()
            r = run_check(user, "duplicate_expenses")
            assert r["status"] == "warn"

    def test_negatives_pass(self, app, expenses):
        with app.app_context():
            r = run_check(expenses, "negative_amounts")
            assert r["status"] == "pass"

    def test_negatives_fail(self, app, user):
        with app.app_context():
            from app.extensions import db
            from app.models import Expense
            e = Expense(user_id=user, amount=-10, description="Neg", date=date.today())
            db.session.add(e)
            db.session.commit()
            r = run_check(user, "negative_amounts")
            assert r["status"] == "fail"

    def test_future_pass(self, app, expenses):
        with app.app_context():
            r = run_check(expenses, "future_dates")
            assert r["status"] == "pass"

    def test_future_warn(self, app, user):
        with app.app_context():
            from app.extensions import db
            from app.models import Expense
            e = Expense(user_id=user, amount=10, description="Future",
                        date=date.today() + timedelta(days=30))
            db.session.add(e)
            db.session.commit()
            r = run_check(user, "future_dates")
            assert r["status"] == "warn"

    def test_missing_desc(self, app, user):
        with app.app_context():
            from app.extensions import db
            from app.models import Expense
            e = Expense(user_id=user, amount=10, description="", date=date.today())
            db.session.add(e)
            db.session.commit()
            r = run_check(user, "missing_descriptions")
            assert r["status"] == "warn"

    def test_checksum(self, app, expenses):
        with app.app_context():
            r = run_check(expenses, "balance_checksum")
            assert r["status"] == "pass"
            assert "checksum" in r["details"]

    def test_invalid_type(self, app, user):
        with app.app_context():
            with pytest.raises(ValueError):
                run_check(user, "bad_check")


class TestReconcile:
    def test_balanced(self, app, expenses):
        with app.app_context():
            r = reconcile(expenses, date.today(), date.today(), 150.0)
            assert r["status"] == "balanced"
            assert r["difference"] == 0

    def test_discrepancy(self, app, expenses):
        with app.app_context():
            r = reconcile(expenses, date.today(), date.today(), 100.0)
            assert r["status"] == "discrepancy"
            assert r["difference"] == 50.0


class TestHistory:
    def test_empty(self, app, user):
        with app.app_context():
            assert get_history(user) == []

    def test_with_checks(self, app, expenses):
        with app.app_context():
            run_all_checks(expenses)
            h = get_history(expenses)
            assert len(h) == len(CHECK_TYPES)

    def test_reconciliations(self, app, expenses):
        with app.app_context():
            reconcile(expenses, date.today(), date.today(), 150.0)
            recs = get_reconciliations(expenses)
            assert len(recs) == 1


class TestAPI:
    def test_types(self, app, user, token):
        client = app.test_client()
        resp = client.get("/integrity/check-types", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_check_all(self, app, user, token):
        client = app.test_client()
        resp = client.post("/integrity/check", json={},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_check_single(self, app, user, token):
        client = app.test_client()
        resp = client.post("/integrity/check", json={"check_type": "orphan_expenses"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_reconcile(self, app, user, token):
        client = app.test_client()
        resp = client.post("/integrity/reconcile",
                           json={"period_start": str(date.today()),
                                 "period_end": str(date.today()),
                                 "expected_total": 0},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_history(self, app, user, token):
        client = app.test_client()
        resp = client.get("/integrity/history", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_reconciliations(self, app, user, token):
        client = app.test_client()
        resp = client.get("/integrity/reconciliations", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
