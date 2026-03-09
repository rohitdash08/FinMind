"""
Tests for PII Export & Delete endpoints (GDPR-ready).
"""

import json
import pytest


# ── helpers ──────────────────────────────────────────────────────────


def _seed_user_data(client, auth_header):
    """Create some sample data for the test user."""
    # Create a category
    r = client.post(
        "/categories",
        json={"name": "Groceries"},
        headers=auth_header,
    )
    assert r.status_code in (200, 201)
    cat_id = r.get_json().get("id") or r.get_json().get("category", {}).get("id")

    # Create an expense
    r = client.post(
        "/expenses",
        json={
            "amount": 42.50,
            "notes": "Weekly shopping",
            "category_id": cat_id,
            "spent_at": "2025-03-01",
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201)

    # Create a bill
    r = client.post(
        "/bills",
        json={
            "name": "Electric bill",
            "amount": 120.00,
            "next_due_date": "2025-04-01",
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code in (200, 201)

    return cat_id


# ── export tests ─────────────────────────────────────────────────────


class TestPIIExport:
    def test_export_requires_auth(self, client):
        r = client.get("/pii/export")
        assert r.status_code in (401, 422)

    def test_export_returns_json_attachment(self, client, auth_header):
        _seed_user_data(client, auth_header)
        r = client.get("/pii/export", headers=auth_header)
        assert r.status_code == 200
        assert "application/json" in r.content_type
        assert "attachment" in r.headers.get("Content-Disposition", "")

    def test_export_contains_user_profile(self, client, auth_header):
        r = client.get("/pii/export", headers=auth_header)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert "user" in data
        assert data["user"]["email"] == "test@example.com"
        # Password hash must NOT be in export
        assert "password_hash" not in data["user"]

    def test_export_contains_expenses(self, client, auth_header):
        _seed_user_data(client, auth_header)
        r = client.get("/pii/export", headers=auth_header)
        data = json.loads(r.data)
        assert len(data["expenses"]) >= 1
        assert data["expenses"][0]["notes"] == "Weekly shopping"

    def test_export_contains_categories(self, client, auth_header):
        _seed_user_data(client, auth_header)
        r = client.get("/pii/export", headers=auth_header)
        data = json.loads(r.data)
        assert len(data["categories"]) >= 1

    def test_export_contains_bills(self, client, auth_header):
        _seed_user_data(client, auth_header)
        r = client.get("/pii/export", headers=auth_header)
        data = json.loads(r.data)
        assert len(data["bills"]) >= 1

    def test_export_has_metadata(self, client, auth_header):
        r = client.get("/pii/export", headers=auth_header)
        data = json.loads(r.data)
        assert data["export_version"] == "1.0"
        assert "exported_at" in data

    def test_export_creates_audit_log(self, client, auth_header):
        r = client.get("/pii/export", headers=auth_header)
        assert r.status_code == 200
        # Export again and check audit logs are in export
        r2 = client.get("/pii/export", headers=auth_header)
        data = json.loads(r2.data)
        actions = [log["action"] for log in data.get("audit_logs", [])]
        assert "pii_export" in actions


# ── delete tests ─────────────────────────────────────────────────────


class TestPIIDelete:
    def test_delete_requires_auth(self, client):
        r = client.post("/pii/delete", json={"confirm": True})
        assert r.status_code in (401, 422)

    def test_delete_requires_confirmation(self, client, auth_header):
        r = client.post("/pii/delete", json={}, headers=auth_header)
        assert r.status_code == 400
        assert "confirm" in r.get_json().get("error", "").lower()

    def test_delete_without_confirm_flag(self, client, auth_header):
        r = client.post("/pii/delete", json={"confirm": False}, headers=auth_header)
        assert r.status_code == 400

    def test_delete_removes_all_data(self, client, auth_header):
        _seed_user_data(client, auth_header)

        # Perform deletion
        r = client.post(
            "/pii/delete",
            json={"confirm": True},
            headers=auth_header,
        )
        assert r.status_code == 200
        body = r.get_json()
        assert body["message"] == "All personal data has been permanently deleted."
        assert body["deleted"]["user"] == 1
        assert body["deleted"]["expenses"] >= 1
        assert body["deleted"]["categories"] >= 1
        assert body["deleted"]["bills"] >= 1

    def test_delete_invalidates_session(self, client, auth_header):
        """After deletion, the user's JWT should no longer work."""
        r = client.post(
            "/pii/delete",
            json={"confirm": True},
            headers=auth_header,
        )
        assert r.status_code == 200

        # Subsequent requests should fail (user gone)
        r = client.get("/pii/export", headers=auth_header)
        # Could be 404 (user not found) or 401/422 depending on JWT validation
        assert r.status_code in (401, 404, 422, 500)

    def test_delete_returns_summary(self, client, auth_header):
        _seed_user_data(client, auth_header)
        r = client.post(
            "/pii/delete",
            json={"confirm": True},
            headers=auth_header,
        )
        body = r.get_json()
        # Verify all expected keys are present
        expected_keys = [
            "user",
            "expenses",
            "categories",
            "bills",
            "reminders",
            "recurring_expenses",
            "ad_impressions",
            "subscriptions",
            "audit_logs",
        ]
        for key in expected_keys:
            assert key in body["deleted"], f"Missing key: {key}"
