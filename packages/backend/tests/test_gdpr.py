"""
Tests for GDPR PII Export & Delete Workflow — Issue #76.

Covers:
  - Export package structure and contents
  - Deletion request lifecycle (initiate, confirm, cancel, status)
  - Audit trail logging
  - Auth isolation
  - Validation errors
"""

import pytest
from flask_jwt_extended import create_access_token
from app.models import User, Expense, Category
from app.extensions import db
from datetime import date


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — bypass Redis (direct JWT, no login endpoint)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture()
def auth_header(client, app_fixture):
    with app_fixture.app_context():
        user = User(
            email="gdpr@example.com",
            password_hash="x",
            preferred_currency="INR",
            role="USER",
        )
        db.session.add(user)
        db.session.commit()
        token = create_access_token(identity=str(user.id))
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_with_data(client, app_fixture, auth_header):
    """Create a user with some expenses and a category."""
    with app_fixture.app_context():
        user = User.query.filter_by(email="gdpr@example.com").first()
        cat = Category(user_id=user.id, name="Food")
        db.session.add(cat)
        db.session.flush()
        exp = Expense(
            user_id=user.id,
            category_id=cat.id,
            amount=500,
            currency="INR",
            expense_type="EXPENSE",
            notes="Lunch",
            spent_at=date.today(),
        )
        db.session.add(exp)
        db.session.commit()
    return auth_header


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

class TestExport:
    def test_export_returns_200(self, client, auth_header):
        r = client.post("/gdpr/export", headers=auth_header)
        assert r.status_code == 200

    def test_export_structure(self, client, auth_header):
        r = client.post("/gdpr/export", headers=auth_header)
        data = r.get_json()
        assert "exported_at" in data
        assert "account" in data
        assert "expenses" in data
        assert "bills" in data
        assert "categories" in data
        assert "reminders" in data

    def test_export_account_fields(self, client, auth_header):
        r = client.post("/gdpr/export", headers=auth_header)
        acct = r.get_json()["account"]
        assert "email" in acct
        assert "preferred_currency" in acct
        assert "created_at" in acct

    def test_export_includes_expenses(self, client, user_with_data):
        r = client.post("/gdpr/export", headers=user_with_data)
        expenses = r.get_json()["expenses"]
        assert len(expenses) == 1
        assert expenses[0]["notes"] == "Lunch"

    def test_export_creates_audit_log(self, client, auth_header):
        client.post("/gdpr/export", headers=auth_header)
        r = client.get("/gdpr/audit", headers=auth_header)
        actions = [e["action"] for e in r.get_json()]
        assert "EXPORT_REQUESTED" in actions

    def test_export_requires_auth(self, client):
        r = client.post("/gdpr/export")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Deletion — initiate
# ─────────────────────────────────────────────────────────────────────────────

class TestDeletionRequest:
    def test_request_deletion_201(self, client, auth_header):
        r = client.post("/gdpr/delete", json={"reason": "Privacy"}, headers=auth_header)
        assert r.status_code == 201

    def test_request_returns_token(self, client, auth_header):
        r = client.post("/gdpr/delete", headers=auth_header)
        data = r.get_json()
        assert "confirmation_token" in data
        assert len(data["confirmation_token"]) > 10

    def test_request_returns_grace_period(self, client, auth_header):
        r = client.post("/gdpr/delete", headers=auth_header)
        data = r.get_json()
        assert data["grace_period_days"] == 7
        assert "grace_period_ends_at" in data

    def test_duplicate_request_rejected(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        r = client.post("/gdpr/delete", headers=auth_header)
        assert r.status_code == 409

    def test_request_requires_auth(self, client):
        r = client.post("/gdpr/delete")
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Deletion — confirm
# ─────────────────────────────────────────────────────────────────────────────

class TestDeletionConfirm:
    def _request(self, client, headers):
        r = client.post("/gdpr/delete", headers=headers)
        return r.get_json()["confirmation_token"]

    def test_confirm_completes_deletion(self, client, auth_header):
        token = self._request(client, auth_header)
        r = client.post("/gdpr/delete/confirm",
                        json={"confirmation_token": token}, headers=auth_header)
        assert r.status_code == 200
        assert "permanently deleted" in r.get_json()["message"]

    def test_confirm_wrong_token_404(self, client, auth_header):
        self._request(client, auth_header)
        r = client.post("/gdpr/delete/confirm",
                        json={"confirmation_token": "wrongtoken"}, headers=auth_header)
        assert r.status_code == 404

    def test_confirm_missing_token_400(self, client, auth_header):
        self._request(client, auth_header)
        r = client.post("/gdpr/delete/confirm", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_confirm_requires_auth(self, client):
        r = client.post("/gdpr/delete/confirm", json={"confirmation_token": "x"})
        assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# Deletion — cancel
# ─────────────────────────────────────────────────────────────────────────────

class TestDeletionCancel:
    def test_cancel_pending_request(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        r = client.post("/gdpr/delete/cancel", headers=auth_header)
        assert r.status_code == 200

    def test_cancel_no_request_404(self, client, auth_header):
        r = client.post("/gdpr/delete/cancel", headers=auth_header)
        assert r.status_code == 404

    def test_cancel_allows_new_request(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        client.post("/gdpr/delete/cancel", headers=auth_header)
        r = client.post("/gdpr/delete", headers=auth_header)
        assert r.status_code == 201


# ─────────────────────────────────────────────────────────────────────────────
# Status
# ─────────────────────────────────────────────────────────────────────────────

class TestDeletionStatus:
    def test_status_no_request(self, client, auth_header):
        r = client.get("/gdpr/delete/status", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["status"] is None

    def test_status_pending(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        r = client.get("/gdpr/delete/status", headers=auth_header)
        assert r.get_json()["status"] == "PENDING"

    def test_status_cancelled(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        client.post("/gdpr/delete/cancel", headers=auth_header)
        r = client.get("/gdpr/delete/status", headers=auth_header)
        assert r.get_json()["status"] == "CANCELLED"


# ─────────────────────────────────────────────────────────────────────────────
# Audit trail
# ─────────────────────────────────────────────────────────────────────────────

class TestAuditTrail:
    def test_audit_empty(self, client, auth_header):
        r = client.get("/gdpr/audit", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_audit_logs_deletion_request(self, client, auth_header):
        client.post("/gdpr/delete", headers=auth_header)
        r = client.get("/gdpr/audit", headers=auth_header)
        actions = [e["action"] for e in r.get_json()]
        assert "DELETION_REQUESTED" in actions

    def test_audit_requires_auth(self, client):
        r = client.get("/gdpr/audit")
        assert r.status_code == 401
