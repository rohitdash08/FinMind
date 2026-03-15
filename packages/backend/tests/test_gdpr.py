"""Tests for GDPR PII Export & Delete Workflow.

Covers:
- PII export package generation
- Deletion request lifecycle (request → confirm → execute)
- Deletion cancellation
- Grace period enforcement
- Duplicate deletion prevention
- Admin-only execute & audit endpoints
- GDPR audit trail immutability
"""

import json
import pytest
from datetime import datetime, timedelta
from app.extensions import db
from app.models import (
    User, Category, Expense, Bill, Reminder,
    RecurringExpense, AdImpression, UserSubscription,
    AuditLog, GDPRAuditLog, DeletionRequest,
    DeletionStatus, GDPRAction, Role,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _register_and_login(client, email="gdpr@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_admin(app, email="admin@test.com", password="admin1234"):
    """Create an admin user and return auth header."""
    from werkzeug.security import generate_password_hash
    with app.app_context():
        u = User(
            email=email,
            password_hash=generate_password_hash(password),
            role=Role.ADMIN.value,
        )
        db.session.add(u)
        db.session.commit()
        uid = u.id
    # Login to get token
    from flask_jwt_extended import create_access_token
    with app.app_context():
        token = create_access_token(identity=str(uid))
    return {"Authorization": f"Bearer {token}"}


def _seed_user_data(app, user_id):
    """Insert rows across all user-owning tables."""
    with app.app_context():
        cat = Category(user_id=user_id, name="Food")
        db.session.add(cat)
        db.session.flush()

        db.session.add(Expense(
            user_id=user_id, category_id=cat.id,
            amount=42.50, notes="lunch",
        ))
        db.session.add(Bill(
            user_id=user_id, name="Electricity",
            amount=100, next_due_date=datetime.utcnow().date(),
            cadence="MONTHLY",
        ))
        db.session.add(Reminder(
            user_id=user_id, message="pay bill",
            send_at=datetime.utcnow(),
        ))
        db.session.add(AdImpression(user_id=user_id, placement="banner"))
        db.session.add(AuditLog(user_id=user_id, action="test_action"))
        db.session.commit()


# ---------------------------------------------------------------------------
# PII Export
# ---------------------------------------------------------------------------

class TestPIIExport:
    def test_export_returns_all_tables(self, app_fixture, client):
        hdr = _register_and_login(client)
        # Seed some data first
        with app_fixture.app_context():
            user = User.query.filter_by(email="gdpr@test.com").first()
            _seed_user_data(app_fixture, user.id)

        r = client.post("/gdpr/export", headers=hdr)
        assert r.status_code == 200
        body = r.get_json()
        export = body["export"]

        # Verify all expected sections are present
        for key in [
            "profile", "categories", "expenses", "recurring_expenses",
            "bills", "reminders", "subscriptions", "ad_impressions",
            "audit_logs",
        ]:
            assert key in export, f"missing key: {key}"

        # Profile should NOT contain password hash
        assert "password_hash" not in export["profile"]
        assert export["profile"]["email"] == "gdpr@test.com"

        # Should have seeded data
        assert len(export["categories"]) >= 1
        assert len(export["expenses"]) >= 1
        assert len(export["bills"]) >= 1

    def test_export_creates_audit_entry(self, app_fixture, client):
        hdr = _register_and_login(client)
        client.post("/gdpr/export", headers=hdr)

        with app_fixture.app_context():
            logs = GDPRAuditLog.query.all()
            actions = [l.action for l in logs]
            assert GDPRAction.EXPORT_REQUESTED.value in actions
            assert GDPRAction.EXPORT_COMPLETED.value in actions

    def test_export_requires_auth(self, client):
        r = client.post("/gdpr/export")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Deletion Request
# ---------------------------------------------------------------------------

class TestDeletionRequest:
    def test_request_deletion(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete", headers=hdr,
                        json={"reason": "moving to another service"})
        assert r.status_code == 201
        body = r.get_json()
        assert "confirmation_token" in body
        assert "grace_period_ends_at" in body
        assert body["message"] == "deletion requested"

    def test_duplicate_request_rejected(self, app_fixture, client):
        hdr = _register_and_login(client)
        r1 = client.post("/gdpr/delete", headers=hdr)
        assert r1.status_code == 201
        r2 = client.post("/gdpr/delete", headers=hdr)
        assert r2.status_code == 400
        assert "already in progress" in r2.get_json()["error"]

    def test_deletion_status(self, app_fixture, client):
        hdr = _register_and_login(client)
        # No request yet
        r = client.get("/gdpr/delete/status", headers=hdr)
        assert r.status_code == 200
        assert r.get_json()["deletion_request"] is None

        # Create request
        client.post("/gdpr/delete", headers=hdr)
        r = client.get("/gdpr/delete/status", headers=hdr)
        assert r.status_code == 200
        status = r.get_json()["deletion_request"]
        assert status["status"] == DeletionStatus.PENDING.value


# ---------------------------------------------------------------------------
# Deletion Confirmation
# ---------------------------------------------------------------------------

class TestDeletionConfirm:
    def test_confirm_deletion(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete", headers=hdr)
        token = r.get_json()["confirmation_token"]

        r = client.post("/gdpr/delete/confirm", headers=hdr,
                        json={"confirmation_token": token})
        assert r.status_code == 200
        assert "confirmed" in r.get_json()["message"]

    def test_invalid_token_rejected(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete/confirm", headers=hdr,
                        json={"confirmation_token": "bogus-token"})
        assert r.status_code == 400

    def test_confirm_without_token(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete/confirm", headers=hdr, json={})
        assert r.status_code == 400
        assert "confirmation_token required" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# Deletion Cancellation
# ---------------------------------------------------------------------------

class TestDeletionCancel:
    def test_cancel_pending_deletion(self, app_fixture, client):
        hdr = _register_and_login(client)
        client.post("/gdpr/delete", headers=hdr)

        r = client.post("/gdpr/delete/cancel", headers=hdr)
        assert r.status_code == 200
        assert r.get_json()["message"] == "deletion cancelled"

    def test_cancel_no_active_request(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete/cancel", headers=hdr)
        assert r.status_code == 400
        assert "no active deletion request" in r.get_json()["error"]

    def test_can_request_again_after_cancel(self, app_fixture, client):
        hdr = _register_and_login(client)
        client.post("/gdpr/delete", headers=hdr)
        client.post("/gdpr/delete/cancel", headers=hdr)
        # Should be able to request again
        r = client.post("/gdpr/delete", headers=hdr)
        assert r.status_code == 201


# ---------------------------------------------------------------------------
# Hard Delete Execution (admin-only)
# ---------------------------------------------------------------------------

class TestDeletionExecute:
    def test_execute_after_grace_period(self, app_fixture, client):
        hdr = _register_and_login(client)
        admin_hdr = _make_admin(app_fixture)

        # Seed data
        with app_fixture.app_context():
            user = User.query.filter_by(email="gdpr@test.com").first()
            _seed_user_data(app_fixture, user.id)
            uid = user.id

        # Request + confirm deletion
        r = client.post("/gdpr/delete", headers=hdr)
        token = r.get_json()["confirmation_token"]
        client.post("/gdpr/delete/confirm", headers=hdr,
                     json={"confirmation_token": token})

        # Expire grace period manually
        with app_fixture.app_context():
            req = DeletionRequest.query.filter_by(user_id=uid).first()
            req.grace_period_ends_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()

        # Execute
        r = client.post(f"/gdpr/delete/execute/{uid}", headers=admin_hdr)
        assert r.status_code == 200

        # Verify data is gone
        with app_fixture.app_context():
            assert Expense.query.filter_by(user_id=uid).count() == 0
            assert Bill.query.filter_by(user_id=uid).count() == 0
            assert Category.query.filter_by(user_id=uid).count() == 0
            assert Reminder.query.filter_by(user_id=uid).count() == 0
            # User is soft-deleted
            user = db.session.get(User, uid)
            assert user.is_deleted is True
            assert "removed.invalid" in user.email

    def test_execute_before_grace_period_fails(self, app_fixture, client):
        hdr = _register_and_login(client)
        admin_hdr = _make_admin(app_fixture)

        with app_fixture.app_context():
            user = User.query.filter_by(email="gdpr@test.com").first()
            uid = user.id

        r = client.post("/gdpr/delete", headers=hdr)
        token = r.get_json()["confirmation_token"]
        client.post("/gdpr/delete/confirm", headers=hdr,
                     json={"confirmation_token": token})

        # Grace period not elapsed → should fail
        r = client.post(f"/gdpr/delete/execute/{uid}", headers=admin_hdr)
        assert r.status_code == 400
        assert "grace period" in r.get_json()["error"]

    def test_non_admin_cannot_execute(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.post("/gdpr/delete/execute/1", headers=hdr)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Admin Audit Trail
# ---------------------------------------------------------------------------

class TestAuditTrail:
    def test_audit_trail_records_actions(self, app_fixture, client):
        hdr = _register_and_login(client)
        admin_hdr = _make_admin(app_fixture)

        # Trigger some GDPR actions
        client.post("/gdpr/export", headers=hdr)
        client.post("/gdpr/delete", headers=hdr)
        client.post("/gdpr/delete/cancel", headers=hdr)

        r = client.get("/gdpr/audit", headers=admin_hdr)
        assert r.status_code == 200
        body = r.get_json()
        assert body["total"] >= 4  # export_req + export_done + delete_req + cancel
        actions = [log["action"] for log in body["audit_logs"]]
        assert GDPRAction.EXPORT_REQUESTED.value in actions
        assert GDPRAction.DELETION_REQUESTED.value in actions
        assert GDPRAction.DELETION_CANCELLED.value in actions

    def test_audit_not_accessible_by_regular_user(self, app_fixture, client):
        hdr = _register_and_login(client)
        r = client.get("/gdpr/audit", headers=hdr)
        assert r.status_code == 403

    def test_audit_pagination(self, app_fixture, client):
        admin_hdr = _make_admin(app_fixture)
        hdr = _register_and_login(client)

        # Generate multiple audit entries
        for _ in range(5):
            client.post("/gdpr/export", headers=hdr)

        r = client.get("/gdpr/audit?page=1&per_page=3", headers=admin_hdr)
        assert r.status_code == 200
        body = r.get_json()
        assert len(body["audit_logs"]) <= 3
        assert body["total"] >= 5

    def test_audit_survives_user_deletion(self, app_fixture, client):
        """GDPR audit logs must persist even after user data is erased."""
        hdr = _register_and_login(client)
        admin_hdr = _make_admin(app_fixture)

        client.post("/gdpr/export", headers=hdr)

        with app_fixture.app_context():
            user = User.query.filter_by(email="gdpr@test.com").first()
            uid = user.id

        # Request + confirm + expire grace + execute
        r = client.post("/gdpr/delete", headers=hdr)
        token = r.get_json()["confirmation_token"]
        client.post("/gdpr/delete/confirm", headers=hdr,
                     json={"confirmation_token": token})
        with app_fixture.app_context():
            req = DeletionRequest.query.filter_by(user_id=uid).first()
            req.grace_period_ends_at = datetime.utcnow() - timedelta(hours=1)
            db.session.commit()
        client.post(f"/gdpr/delete/execute/{uid}", headers=admin_hdr)

        # Audit logs should still exist with original email
        r = client.get(f"/gdpr/audit?user_id={uid}", headers=admin_hdr)
        assert r.status_code == 200
        body = r.get_json()
        assert body["total"] >= 1
        # At least one log should still reference the original email
        emails = [log["user_email"] for log in body["audit_logs"]]
        assert "gdpr@test.com" in emails
