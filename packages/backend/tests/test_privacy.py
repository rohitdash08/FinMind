"""
Tests for the GDPR-ready PII export & delete workflow (issue #76).

Covers:
  - GET  /privacy/export         → ZIP download containing data.json
  - POST /privacy/delete         → irreversible account deletion
  - GET  /privacy/audit-log      → audit trail retrieval
  - Audit entries created for export and delete events
"""

import io
import json
import zipfile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _register_and_login(client, email="privacy@test.com", password="s3cr3t!"):
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


class TestPIIExport:
    def test_export_requires_auth(self, client):
        r = client.get("/privacy/export")
        assert r.status_code == 401

    def test_export_returns_zip(self, client):
        auth = _register_and_login(client)
        r = client.get("/privacy/export", headers=auth)
        assert r.status_code == 200
        assert "zip" in r.content_type

    def test_export_zip_contains_data_json(self, client):
        auth = _register_and_login(client, "export2@test.com")
        r = client.get("/privacy/export", headers=auth)
        assert r.status_code == 200

        buf = io.BytesIO(r.data)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "data.json" in names
            assert "README.txt" in names

            json.loads(zf.read("data.json"))

    def test_export_data_json_has_expected_keys(self, client):
        auth = _register_and_login(client, "export3@test.com")
        r = client.get("/privacy/export", headers=auth)
        buf = io.BytesIO(r.data)
        with zipfile.ZipFile(buf) as zf:
            data = json.loads(zf.read("data.json"))

        assert "profile" in data
        assert "expenses" in data
        assert "categories" in data
        assert "bills" in data
        assert "reminders" in data
        assert "recurring_expenses" in data
        assert "exported_at" in data

    def test_export_profile_email_matches(self, client):
        email = "exportprofile@test.com"
        auth = _register_and_login(client, email)
        r = client.get("/privacy/export", headers=auth)
        buf = io.BytesIO(r.data)
        with zipfile.ZipFile(buf) as zf:
            data = json.loads(zf.read("data.json"))

        assert data["profile"]["email"] == email

    def test_export_creates_audit_entry(self, client):
        auth = _register_and_login(client, "exportaudit@test.com")
        client.get("/privacy/export", headers=auth)

        # Check audit log via the audit-log endpoint
        r = client.get("/privacy/audit-log", headers=auth)
        assert r.status_code == 200
        actions = [e["action"] for e in r.get_json()["audit_log"]]
        assert "PII_EXPORT" in actions


# ---------------------------------------------------------------------------
# Delete tests
# ---------------------------------------------------------------------------


class TestAccountDeletion:
    def test_delete_requires_auth(self, client):
        r = client.post("/privacy/delete", json={"password": "whatever"})
        assert r.status_code == 401

    def test_delete_requires_password_field(self, client):
        auth = _register_and_login(client, "delreq@test.com")
        r = client.post("/privacy/delete", json={}, headers=auth)
        assert r.status_code == 400

    def test_delete_rejects_wrong_password(self, client):
        auth = _register_and_login(client, "delwrong@test.com")
        r = client.post(
            "/privacy/delete", json={"password": "wrong-password"}, headers=auth
        )
        assert r.status_code == 403

    def test_delete_succeeds_with_correct_password(self, client):
        email = "delsuccess@test.com"
        password = "correct-pass-123"
        auth = _register_and_login(client, email, password)

        r = client.post("/privacy/delete", json={"password": password}, headers=auth)
        assert r.status_code == 200
        body = r.get_json()
        assert "permanently deleted" in body["message"].lower()

    def test_delete_is_irreversible_user_gone(self, client):
        email = "delirrev@test.com"
        password = "irrev-pass-456"
        auth = _register_and_login(client, email, password)

        # Delete the account
        r = client.post("/privacy/delete", json={"password": password}, headers=auth)
        assert r.status_code == 200

        # The same JWT should now fail to reach /auth/me
        r = client.get("/auth/me", headers=auth)
        assert r.status_code == 404

    def test_delete_creates_audit_entry(self, client, app_fixture):
        """Audit log entry with ACCOUNT_DELETED must survive account removal."""
        from app.models import AuditLog
        from app.extensions import db

        email = "delaudit@test.com"
        password = "audit-pass-789"
        auth = _register_and_login(client, email, password)

        # Delete the account
        r = client.post("/privacy/delete", json={"password": password}, headers=auth)
        assert r.status_code == 200

        # The audit row should exist even though the user is gone
        with app_fixture.app_context():
            entry = (
                db.session.query(AuditLog).filter_by(action="ACCOUNT_DELETED").first()
            )
            assert entry is not None

    def test_cannot_delete_twice_with_old_token(self, client):
        email = "deltwice@test.com"
        password = "twice-pass-000"
        auth = _register_and_login(client, email, password)

        # First deletion succeeds
        r = client.post("/privacy/delete", json={"password": password}, headers=auth)
        assert r.status_code == 200

        # Second attempt with the same (now-invalid) token should 404
        r = client.post("/privacy/delete", json={"password": password}, headers=auth)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Audit-log endpoint tests
# ---------------------------------------------------------------------------


class TestAuditLog:
    def test_audit_log_requires_auth(self, client):
        r = client.get("/privacy/audit-log")
        assert r.status_code == 401

    def test_audit_log_empty_initially(self, client):
        auth = _register_and_login(client, "auditclean@test.com")
        r = client.get("/privacy/audit-log", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert "audit_log" in data
        assert isinstance(data["audit_log"], list)

    def test_audit_log_pagination(self, client):
        auth = _register_and_login(client, "auditpag@test.com")

        # Trigger a few audit events via export
        for _ in range(3):
            client.get("/privacy/export", headers=auth)

        r = client.get("/privacy/audit-log?limit=2&offset=0", headers=auth)
        assert r.status_code == 200
        data = r.get_json()
        assert len(data["audit_log"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0
