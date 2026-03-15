"""Tests for the GDPR PII Export & Delete Workflow (Issue #76)."""
import pytest
from flask_jwt_extended import create_access_token
from app.models import User
from app.extensions import db as _db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_user(app, email="gdpr@example.com", password="pass1234"):
    """Create a user in the DB and return (user_id, jwt_header)."""
    from werkzeug.security import generate_password_hash

    with app.app_context():
        existing = _db.session.query(User).filter_by(email=email).first()
        if existing:
            uid = existing.id
        else:
            u = User(
                email=email,
                password_hash=generate_password_hash(password),
                preferred_currency="USD",
            )
            _db.session.add(u)
            _db.session.commit()
            uid = u.id
        token = create_access_token(identity=str(uid))
    return uid, {"Authorization": f"Bearer {token}"}


def _seed_data(uid, app):
    """Seed a category and an expense directly into the DB (bypass Redis cache)."""
    from datetime import date
    from app.models import Category, Expense

    with app.app_context():
        cat = Category(user_id=uid, name="Food")
        _db.session.add(cat)
        _db.session.flush()
        exp = Expense(
            user_id=uid,
            category_id=cat.id,
            amount=10,
            currency="USD",
            expense_type="EXPENSE",
            notes="Lunch",
            spent_at=date(2026, 3, 1),
        )
        _db.session.add(exp)
        _db.session.commit()
        return cat.id


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


def test_export_requires_auth(client):
    r = client.post("/gdpr/export")
    assert r.status_code == 401


def test_export_empty_user(client, app_fixture):
    _uid, auth = _make_user(app_fixture, "empty@gdpr.test")
    r = client.post("/gdpr/export", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert "exported_at" in data
    assert "user" in data
    assert data["expenses"] == []
    assert data["bills"] == []
    assert data["categories"] == []
    assert data["reminders"] == []
    assert data["recurring_expenses"] == []


def test_export_contains_user_pii(client, app_fixture):
    _uid, auth = _make_user(app_fixture, "piichk@gdpr.test")
    r = client.post("/gdpr/export", headers=auth)
    assert r.status_code == 200
    user_data = r.get_json()["user"]
    assert "email" in user_data
    assert "id" in user_data
    assert "created_at" in user_data
    # password_hash must NOT be included in the export
    assert "password_hash" not in user_data


def test_export_includes_seeded_data(client, app_fixture):
    uid, auth = _make_user(app_fixture, "seed@gdpr.test")
    _seed_data(uid, app_fixture)
    r = client.post("/gdpr/export", headers=auth)
    assert r.status_code == 200
    pkg = r.get_json()
    assert len(pkg["expenses"]) == 1
    assert pkg["expenses"][0]["notes"] == "Lunch"
    assert len(pkg["categories"]) == 1
    assert pkg["categories"][0]["name"] == "Food"


def test_export_audit_logged(client, app_fixture):
    uid, auth = _make_user(app_fixture, "auditex@gdpr.test")
    client.post("/gdpr/export", headers=auth)
    with app_fixture.app_context():
        from app.models import AuditLog
        logs = _db.session.query(AuditLog).filter_by(
            user_id=uid, action="GDPR_EXPORT_REQUESTED"
        ).all()
        assert len(logs) >= 1


# ---------------------------------------------------------------------------
# Delete-initiation tests
# ---------------------------------------------------------------------------


def test_delete_requires_auth(client):
    r = client.post("/gdpr/delete")
    assert r.status_code == 401


def test_delete_initiate(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    _uid, auth = _make_user(app_fixture, "delinit@gdpr.test")
    _pending_deletions.clear()
    r = client.post("/gdpr/delete", headers=auth)
    assert r.status_code == 202
    data = r.get_json()
    assert "requested_at" in data
    assert "confirm" in data["message"].lower()


def test_delete_initiate_idempotent(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    _uid, auth = _make_user(app_fixture, "delidem@gdpr.test")
    _pending_deletions.clear()
    r1 = client.post("/gdpr/delete", headers=auth)
    r2 = client.post("/gdpr/delete", headers=auth)
    assert r1.status_code == 202
    assert r2.status_code == 200
    assert r2.get_json()["requested_at"] == r1.get_json()["requested_at"]


def test_delete_audit_logged(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    uid, auth = _make_user(app_fixture, "delaudit@gdpr.test")
    _pending_deletions.clear()
    client.post("/gdpr/delete", headers=auth)
    with app_fixture.app_context():
        from app.models import AuditLog
        logs = _db.session.query(AuditLog).filter_by(
            user_id=uid, action="GDPR_DELETE_REQUESTED"
        ).all()
        assert len(logs) >= 1


# ---------------------------------------------------------------------------
# Confirm-delete tests
# ---------------------------------------------------------------------------


def test_confirm_delete_without_initiation(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    _uid, auth = _make_user(app_fixture, "nodelpend@gdpr.test")
    _pending_deletions.clear()
    r = client.delete("/gdpr/delete/confirm", headers=auth)
    assert r.status_code == 409


def test_confirm_delete_full_flow(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    uid, auth = _make_user(app_fixture, "hardel@gdpr.test")
    _pending_deletions.clear()
    _seed_data(uid, app_fixture)

    # Export before deletion works
    r_export = client.post("/gdpr/export", headers=auth)
    assert r_export.status_code == 200
    assert len(r_export.get_json()["expenses"]) == 1

    # Initiate deletion
    r_init = client.post("/gdpr/delete", headers=auth)
    assert r_init.status_code == 202

    # Confirm hard-delete
    r_confirm = client.delete("/gdpr/delete/confirm", headers=auth)
    assert r_confirm.status_code == 200
    assert "permanently deleted" in r_confirm.get_json()["message"].lower()

    # Subsequent requests with the same token should fail (user deleted)
    r_after = client.post("/gdpr/export", headers=auth)
    assert r_after.status_code == 404


def test_confirm_delete_audit_logged(client, app_fixture):
    from app.routes.gdpr import _pending_deletions
    uid, auth = _make_user(app_fixture, "confirmaudit@gdpr.test")
    _pending_deletions.clear()
    client.post("/gdpr/delete", headers=auth)
    client.delete("/gdpr/delete/confirm", headers=auth)
    with app_fixture.app_context():
        from app.models import AuditLog
        logs = _db.session.query(AuditLog).filter_by(
            user_id=uid, action="GDPR_DELETE_CONFIRMED"
        ).all()
        assert len(logs) >= 1


def test_confirm_delete_clears_pending_state(client, app_fixture):
    """After hard-delete, the pending entry must be removed."""
    from app.routes.gdpr import _pending_deletions
    uid, auth = _make_user(app_fixture, "clearpend@gdpr.test")
    _pending_deletions.clear()
    client.post("/gdpr/delete", headers=auth)
    client.delete("/gdpr/delete/confirm", headers=auth)
    # After deletion the user is gone: subsequent attempt returns 404
    r = client.delete("/gdpr/delete/confirm", headers=auth)
    assert r.status_code == 404
    # And the pending dict must not retain a stale entry for deleted user
    assert uid not in _pending_deletions
