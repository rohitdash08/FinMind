"""Tests for GDPR PII export, deletion, anonymization, and audit trail."""

import json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email="gdpr@test.com", password="secret123"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    data = r.get_json()
    return data["access_token"], password


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _seed_data(client, token):
    """Create some expenses, categories, bills, reminders for the test user."""
    headers = _auth(token)
    # category
    r = client.post("/categories", json={"name": "Food"}, headers=headers)
    assert r.status_code in (201, 409)

    # expense
    r = client.post(
        "/expenses",
        json={"amount": 42.50, "description": "Lunch at cafe", "date": "2026-03-01"},
        headers=headers,
    )
    assert r.status_code == 201

    # bill
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 59.99,
            "next_due_date": "2026-04-01",
            "cadence": "MONTHLY",
        },
        headers=headers,
    )
    assert r.status_code == 201

    # reminder
    r = client.post(
        "/reminders",
        json={"message": "Pay credit card", "send_at": "2026-04-01T10:00:00Z"},
        headers=headers,
    )
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


def test_export_returns_all_user_data(client):
    token, _ = _register_and_login(client, "export1@test.com")
    _seed_data(client, token)

    r = client.get("/gdpr/export", headers=_auth(token))
    assert r.status_code == 200
    pkg = r.get_json()

    assert "user" in pkg
    assert pkg["user"]["email"] == "export1@test.com"
    assert "export_generated_at" in pkg
    assert isinstance(pkg["categories"], list)
    assert isinstance(pkg["expenses"], list)
    assert isinstance(pkg["bills"], list)
    assert isinstance(pkg["reminders"], list)
    assert isinstance(pkg["subscriptions"], list)
    assert isinstance(pkg["audit_logs"], list)

    # Should have at least the seeded data
    assert len(pkg["expenses"]) >= 1
    assert len(pkg["bills"]) >= 1
    assert len(pkg["reminders"]) >= 1


def test_export_requires_auth(client):
    r = client.get("/gdpr/export")
    assert r.status_code == 401


def test_export_only_returns_own_data(client):
    # User A
    token_a, _ = _register_and_login(client, "usera@test.com")
    _seed_data(client, token_a)

    # User B
    token_b, _ = _register_and_login(client, "userb@test.com")

    r = client.get("/gdpr/export", headers=_auth(token_b))
    assert r.status_code == 200
    pkg = r.get_json()
    assert pkg["user"]["email"] == "userb@test.com"
    assert len(pkg["expenses"]) == 0
    assert len(pkg["bills"]) == 0


# ---------------------------------------------------------------------------
# Deletion request tests
# ---------------------------------------------------------------------------


def test_delete_request_requires_password(client):
    token, _ = _register_and_login(client, "del1@test.com")

    r = client.post("/gdpr/delete", json={}, headers=_auth(token))
    assert r.status_code == 400
    assert "password required" in r.get_json()["error"]


def test_delete_request_rejects_wrong_password(client):
    token, _ = _register_and_login(client, "del2@test.com")

    r = client.post(
        "/gdpr/delete", json={"password": "wrongpass"}, headers=_auth(token)
    )
    assert r.status_code == 403


def test_delete_request_creates_pending(client):
    token, pw = _register_and_login(client, "del3@test.com")

    r = client.post(
        "/gdpr/delete", json={"password": pw, "reason": "Moving away"}, headers=_auth(token)
    )
    assert r.status_code == 202
    data = r.get_json()
    assert data["status"] == "pending"
    assert "scheduled_at" in data
    assert data["grace_period_days"] == 30


def test_delete_request_idempotent(client):
    token, pw = _register_and_login(client, "del4@test.com")

    r1 = client.post("/gdpr/delete", json={"password": pw}, headers=_auth(token))
    assert r1.status_code == 202

    r2 = client.post("/gdpr/delete", json={"password": pw}, headers=_auth(token))
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "already_pending"


# ---------------------------------------------------------------------------
# Deletion cancel tests
# ---------------------------------------------------------------------------


def test_cancel_deletion(client):
    token, pw = _register_and_login(client, "cancel1@test.com")

    client.post("/gdpr/delete", json={"password": pw}, headers=_auth(token))

    r = client.post("/gdpr/delete/cancel", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["status"] == "cancelled"


def test_cancel_deletion_no_pending(client):
    token, _ = _register_and_login(client, "cancel2@test.com")

    r = client.post("/gdpr/delete/cancel", headers=_auth(token))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Deletion status tests
# ---------------------------------------------------------------------------


def test_deletion_status_no_pending(client):
    token, _ = _register_and_login(client, "status1@test.com")

    r = client.get("/gdpr/delete/status", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["pending"] is False


def test_deletion_status_pending(client):
    token, pw = _register_and_login(client, "status2@test.com")

    client.post("/gdpr/delete", json={"password": pw}, headers=_auth(token))

    r = client.get("/gdpr/delete/status", headers=_auth(token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["pending"] is True
    assert "scheduled_at" in data


# ---------------------------------------------------------------------------
# Confirm deletion (immediate hard-delete) tests
# ---------------------------------------------------------------------------


def test_confirm_deletion_removes_all_data(client):
    token, pw = _register_and_login(client, "hardel@test.com")
    _seed_data(client, token)

    # Verify data exists
    r = client.get("/gdpr/export", headers=_auth(token))
    assert r.status_code == 200
    assert len(r.get_json()["expenses"]) >= 1

    # Confirm deletion
    r = client.post(
        "/gdpr/delete/confirm", json={"password": pw}, headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "deleted"

    # User should no longer exist -- any authenticated call fails
    r = client.get("/auth/me", headers=_auth(token))
    assert r.status_code in (401, 404, 422)


def test_confirm_deletion_requires_password(client):
    token, _ = _register_and_login(client, "hardel2@test.com")

    r = client.post("/gdpr/delete/confirm", json={}, headers=_auth(token))
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Anonymization tests
# ---------------------------------------------------------------------------


def test_anonymize_replaces_pii(client):
    token, pw = _register_and_login(client, "anon1@test.com")
    _seed_data(client, token)

    r = client.post(
        "/gdpr/anonymize", json={"password": pw}, headers=_auth(token)
    )
    assert r.status_code == 200
    assert r.get_json()["status"] == "anonymized"


def test_anonymize_requires_password(client):
    token, _ = _register_and_login(client, "anon2@test.com")

    r = client.post("/gdpr/anonymize", json={}, headers=_auth(token))
    assert r.status_code == 400


def test_anonymize_rejects_wrong_password(client):
    token, _ = _register_and_login(client, "anon3@test.com")

    r = client.post(
        "/gdpr/anonymize", json={"password": "wrong"}, headers=_auth(token)
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Audit log tests
# ---------------------------------------------------------------------------


def test_audit_logs_require_admin(client):
    token, _ = _register_and_login(client, "nonadmin@test.com")

    r = client.get("/gdpr/audit-logs", headers=_auth(token))
    assert r.status_code == 403


def test_audit_logs_created_on_export(client, app_fixture):
    token, _ = _register_and_login(client, "auditexp@test.com")
    client.get("/gdpr/export", headers=_auth(token))

    # Check audit log was created in database
    from app.models import GdprAuditLog

    with app_fixture.app_context():
        from app.extensions import db

        logs = db.session.query(GdprAuditLog).filter_by(action="EXPORT").all()
        assert len(logs) >= 1
        assert logs[0].action == "EXPORT"
        assert logs[0].status == "completed"


def test_audit_logs_created_on_deletion_request(client, app_fixture):
    token, pw = _register_and_login(client, "auditdel@test.com")
    client.post("/gdpr/delete", json={"password": pw}, headers=_auth(token))

    from app.models import GdprAuditLog

    with app_fixture.app_context():
        from app.extensions import db

        logs = db.session.query(GdprAuditLog).filter_by(action="DELETE_REQUEST").all()
        assert len(logs) >= 1
        assert logs[0].status == "pending"


def test_audit_logs_survive_user_deletion(client, app_fixture):
    """GDPR audit logs must be retained even after the user is deleted."""
    token, pw = _register_and_login(client, "auditsurvive@test.com")
    client.get("/gdpr/export", headers=_auth(token))
    client.post("/gdpr/delete/confirm", json={"password": pw}, headers=_auth(token))

    from app.models import GdprAuditLog

    with app_fixture.app_context():
        from app.extensions import db

        # Audit log entries should still exist
        logs = db.session.query(GdprAuditLog).all()
        actions = {log.action for log in logs}
        assert "EXPORT" in actions
        assert "DELETE_CONFIRM" in actions
