"""Tests for GDPR data export and account deletion endpoints."""

import io
import json
import zipfile

import pytest


def _register_and_login(client, email="gdpr@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    tokens = r.get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _seed_data(client, headers):
    """Create some expenses, categories, bills so export has content."""
    client.post("/categories", json={"name": "Food"}, headers=headers)
    client.post(
        "/expenses",
        json={"amount": 42.50, "notes": "lunch", "spent_at": "2025-01-15"},
        headers=headers,
    )
    client.post(
        "/bills",
        json={
            "name": "Netflix",
            "amount": 15.99,
            "next_due_date": "2025-02-01",
            "cadence": "MONTHLY",
        },
        headers=headers,
    )


class TestExport:
    def test_export_returns_zip(self, client):
        headers = _register_and_login(client)
        _seed_data(client, headers)

        r = client.get("/user/export", headers=headers)
        assert r.status_code == 200
        assert r.content_type == "application/zip"

        zf = zipfile.ZipFile(io.BytesIO(r.data))
        assert "finmind_export.json" in zf.namelist()

        data = json.loads(zf.read("finmind_export.json"))
        assert data["user"]["email"] == "gdpr@test.com"
        assert "password_hash" not in data["user"]
        assert len(data["expenses"]) >= 1
        assert len(data["categories"]) >= 1
        assert len(data["bills"]) >= 1
        assert "exported_at" in data

    def test_export_requires_auth(self, client):
        r = client.get("/user/export")
        assert r.status_code == 401


class TestDeleteAccount:
    def test_delete_removes_all_data(self, client):
        headers = _register_and_login(client, "delete@test.com")
        _seed_data(client, headers)

        r = client.delete("/user", headers=headers)
        assert r.status_code == 200
        assert r.get_json()["message"] == "account permanently deleted"

        # Token should now be invalid (user gone)
        r = client.get("/auth/me", headers=headers)
        assert r.status_code == 404

    def test_delete_requires_auth(self, client):
        r = client.delete("/user")
        assert r.status_code == 401
