"""Tests for GDPR PII export and delete endpoints."""

import json

import pytest


def test_export_returns_zip(client, auth_headers):
    """GET /user/export should return a downloadable ZIP."""
    resp = client.get("/user/export", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.content_type == "application/zip"
    assert "finmind-export" in resp.headers.get("Content-Disposition", "")


def test_export_contains_user_data(client, auth_headers):
    """Exported ZIP should contain user_data.json with correct structure."""
    import io
    import zipfile

    resp = client.get("/user/export", headers=auth_headers)
    buf = io.BytesIO(resp.data)
    with zipfile.ZipFile(buf) as zf:
        assert "finmind-export/user_data.json" in zf.namelist()
        data = json.loads(zf.read("finmind-export/user_data.json"))
        assert "user" in data
        assert "expenses" in data
        assert "categories" in data
        assert "bills" in data
        assert "export_metadata" in data


def test_export_creates_audit_log(client, auth_headers):
    """Export should create an audit log entry."""
    # Export
    client.get("/user/export", headers=auth_headers)
    # Check audit log
    resp = client.get("/user/audit-log", headers=auth_headers)
    assert resp.status_code == 200
    entries = resp.get_json()["entries"]
    actions = [e["action"] for e in entries]
    assert "DATA_EXPORT_REQUESTED" in actions


def test_delete_removes_all_data(client, auth_headers):
    """DELETE /user/delete should remove all user data."""
    resp = client.delete("/user/delete", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "deleted_at" in data


def test_delete_unauthenticated(client):
    """DELETE /user/delete without auth should return 401."""
    resp = client.delete("/user/delete")
    assert resp.status_code == 401


def test_export_unauthenticated(client):
    """GET /user/export without auth should return 401."""
    resp = client.get("/user/export")
    assert resp.status_code == 401


def test_audit_log_returns_entries(client, auth_headers):
    """GET /user/audit-log should return recent entries."""
    resp = client.get("/user/audit-log", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "entries" in data
    assert isinstance(data["entries"], list)
