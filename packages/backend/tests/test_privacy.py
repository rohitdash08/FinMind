"""Tests for GDPR privacy endpoints (PII export & delete)."""

from datetime import date, timedelta


def _seed_full_profile(client, auth_header):
    """Seed a rich user profile with categories, expenses, bills, etc."""
    # Category
    r = client.post("/categories", json={"name": "Transport"}, headers=auth_header)
    assert r.status_code == 201
    cat_id = r.get_json()["id"]

    # Expenses
    for desc, etype in [("Salary", "INCOME"), ("Bus fare", "EXPENSE")]:
        r = client.post(
            "/expenses",
            json={
                "amount": 1000 if etype == "INCOME" else 50,
                "description": desc,
                "date": date.today().isoformat(),
                "expense_type": etype,
                "category_id": cat_id if etype == "EXPENSE" else None,
            },
            headers=auth_header,
        )
        assert r.status_code == 201

    # Bill
    r = client.post(
        "/bills",
        json={
            "name": "Electricity",
            "amount": 120,
            "next_due_date": (date.today() + timedelta(days=5)).isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201


# ── Export tests ──────────────────────────────────────────────────────────────


def test_export_empty_user(client, auth_header):
    """A freshly registered user should still return a valid export."""
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["export_version"] == "1.0"
    assert "exported_at" in data
    assert "profile" in data
    assert data["profile"]["email"] == "test@example.com"
    assert isinstance(data["categories"], list)
    assert isinstance(data["expenses"], list)
    assert isinstance(data["bills"], list)


def test_export_with_data(client, auth_header):
    """After seeding data, the export should contain all records."""
    _seed_full_profile(client, auth_header)
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()

    assert len(data["categories"]) >= 1
    assert len(data["expenses"]) >= 2
    assert len(data["bills"]) >= 1

    # Verify expense fields are present
    expense = data["expenses"][0]
    assert "amount" in expense
    assert "currency" in expense
    assert "spent_at" in expense

    # Verify bill fields
    bill = data["bills"][0]
    assert bill["name"] == "Electricity"


def test_export_requires_auth(client):
    """Export endpoint should return 401 without auth."""
    r = client.get("/privacy/export")
    assert r.status_code == 401


# ── Delete tests ──────────────────────────────────────────────────────────────


def test_delete_requires_confirmation(client, auth_header):
    """Delete should reject requests without explicit confirmation."""
    r = client.post("/privacy/delete", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "confirm" in r.get_json()["error"]


def test_delete_without_body(client, auth_header):
    """Delete should handle missing body gracefully."""
    r = client.post(
        "/privacy/delete",
        headers={**auth_header, "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_delete_user_data(client, auth_header):
    """After deletion, user data should be completely removed."""
    _seed_full_profile(client, auth_header)

    # Verify data exists first
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()["expenses"]) >= 2

    # Perform deletion
    r = client.post(
        "/privacy/delete", json={"confirm": True}, headers=auth_header
    )
    assert r.status_code == 200
    assert "permanently deleted" in r.get_json()["message"].lower()

    # Token is still valid but user no longer exists, so export should fail
    r = client.get("/privacy/export", headers=auth_header)
    assert r.status_code == 404


def test_delete_requires_auth(client):
    """Delete endpoint should return 401 without auth."""
    r = client.post("/privacy/delete", json={"confirm": True})
    assert r.status_code == 401


def test_delete_is_irreversible(client, auth_header):
    """After deletion, login should fail."""
    r = client.post(
        "/privacy/delete", json={"confirm": True}, headers=auth_header
    )
    assert r.status_code == 200

    # Attempt login — should fail
    r = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "password123"},
    )
    assert r.status_code in (401, 404)
