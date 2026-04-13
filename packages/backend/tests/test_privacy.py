"""Tests for PII export & deletion endpoints."""

import json


def _seed_expense(client, auth_header, amount=50, desc="Test expense"):
    r = client.post("/expenses", json={"amount": amount, "description": desc, "expense_type": "EXPENSE"}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


def _seed_category(client, auth_header, name="TestCat"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code == 201
    return r.get_json()


# 1. Auth required for export
def test_export_requires_auth(client):
    r = client.get("/privacy/export")
    assert r.status_code in (401, 422)


# 2. Auth required for delete
def test_delete_requires_auth(client):
    r = client.post("/privacy/delete", json={"confirm": True})
    assert r.status_code in (401, 422)


# 3. Export returns user data
def test_export_returns_data(client, auth_header):
    _seed_expense(client, auth_header, 100, "Groceries")
    _seed_category(client, auth_header, "Food")

    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "json_data" in data
    assert "csv_data" in data
    assert "summary" in data
    assert data["summary"]["expenses"] >= 1
    assert data["summary"]["categories"] >= 1
    assert data["summary"]["profile"] == 1

    parsed = json.loads(data["json_data"])
    assert parsed["profile"]["email"] == "test@example.com"
    assert len(parsed["expenses"]) >= 1


# 4. Export CSV contains expenses
def test_export_csv_format(client, auth_header):
    _seed_expense(client, auth_header, 75, "Coffee")
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    csv_data = r.get_json()["csv_data"]
    assert "amount" in csv_data
    assert "75" in csv_data


# 5. Delete requires confirmation
def test_delete_requires_confirmation(client, auth_header):
    r = client.post("/privacy/delete", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "confirm" in r.get_json()["error"].lower()


# 6. Delete removes all data
def test_delete_removes_all_data(client, auth_header):
    _seed_expense(client, auth_header, 200, "Dinner")
    _seed_category(client, auth_header, "Dining")

    r = client.post("/privacy/delete", json={"confirm": True}, headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["message"] == "all data permanently deleted"
    assert "deleted" in data
    assert data["deleted"]["user"] == 1
    assert data["deleted"]["expenses"] >= 1


# 7. Audit log tracks export
def test_audit_log_tracks_export(client, auth_header):
    client.get("/privacy/export", headers=auth_header)
    r = client.get("/privacy/audit-log", headers=auth_header)
    assert r.status_code == 200
    entries = r.get_json()
    actions = [e["action"] for e in entries]
    assert "pii_export" in actions


# 8. Empty export for fresh user
def test_empty_export(client, auth_header):
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["summary"]["expenses"] == 0
    assert data["summary"]["bills"] == 0
