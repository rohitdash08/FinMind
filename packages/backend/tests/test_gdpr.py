"""Tests for GDPR export & delete endpoints."""
import io
import json
import zipfile

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _auth_headers(client, email="gdpr@example.com", password="testpass123"):
    client.post(
        "/auth/register",
        json={"email": email, "password": password},
    )
    resp = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    token = resp.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ── Export tests ──────────────────────────────────────────────────────────────

class TestGDPRExport:
    def test_export_returns_zip(self, client):
        headers = _auth_headers(client)
        resp = client.get("/gdpr/export", headers=headers)
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert b"PK" in resp.data  # ZIP magic bytes

    def test_export_zip_contains_expected_files(self, client):
        headers = _auth_headers(client, email="export2@example.com")
        resp = client.get("/gdpr/export", headers=headers)
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        names = zf.namelist()
        assert "profile.json" in names
        assert "expenses.json" in names
        assert "categories.json" in names
        assert "recurring_expenses.json" in names
        assert "bills.json" in names
        assert "audit_log.json" in names
        assert "README.txt" in names

    def test_export_profile_contains_email(self, client):
        email = "export3@example.com"
        headers = _auth_headers(client, email=email)
        resp = client.get("/gdpr/export", headers=headers)
        zf = zipfile.ZipFile(io.BytesIO(resp.data))
        profile = json.loads(zf.read("profile.json"))
        assert profile["email"] == email

    def test_export_creates_audit_entry(self, client):
        headers = _auth_headers(client, email="export4@example.com")
        client.get("/gdpr/export", headers=headers)
        audit_resp = client.get("/gdpr/audit-log", headers=headers)
        log = audit_resp.get_json()["audit_log"]
        assert any(e["action"] == "EXPORT_REQUESTED" for e in log)

    def test_export_requires_auth(self, client):
        resp = client.get("/gdpr/export")
        assert resp.status_code == 401


# ── Delete tests ──────────────────────────────────────────────────────────────

class TestGDPRDelete:
    def test_delete_returns_200(self, client):
        headers = _auth_headers(client, email="del1@example.com")
        resp = client.delete("/gdpr/account", headers=headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deleted"] is True

    def test_delete_removes_user_data(self, client):
        headers = _auth_headers(client, email="del2@example.com")
        client.delete("/gdpr/account", headers=headers)
        # Login should now fail
        login = client.post(
            "/auth/login",
            json={"email": "del2@example.com", "password": "testpass123"},
        )
        assert login.status_code == 401

    def test_delete_response_includes_counts(self, client):
        headers = _auth_headers(client, email="del3@example.com")
        resp = client.delete("/gdpr/account", headers=headers)
        data = resp.get_json()
        assert "records_removed" in data
        assert "user" in data["records_removed"]

    def test_delete_requires_auth(self, client):
        resp = client.delete("/gdpr/account")
        assert resp.status_code == 401

    def test_delete_is_irreversible(self, client):
        headers = _auth_headers(client, email="del4@example.com")
        client.delete("/gdpr/account", headers=headers)
        # Second delete should 404 (user gone)
        resp = client.delete("/gdpr/account", headers=headers)
        assert resp.status_code in (401, 404)


# ── Audit log tests ───────────────────────────────────────────────────────────

class TestGDPRAuditLog:
    def test_audit_log_empty_initially(self, client):
        headers = _auth_headers(client, email="audit1@example.com")
        resp = client.get("/gdpr/audit-log", headers=headers)
        assert resp.status_code == 200
        assert resp.get_json()["audit_log"] == []

    def test_audit_log_records_export(self, client):
        headers = _auth_headers(client, email="audit2@example.com")
        client.get("/gdpr/export", headers=headers)
        resp = client.get("/gdpr/audit-log", headers=headers)
        log = resp.get_json()["audit_log"]
        assert len(log) >= 1
        assert log[0]["action"] == "EXPORT_REQUESTED"

    def test_audit_log_requires_auth(self, client):
        resp = client.get("/gdpr/audit-log")
        assert resp.status_code == 401
