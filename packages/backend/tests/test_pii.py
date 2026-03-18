"""Tests for PII export, delete, and audit-log endpoints."""

import json
from datetime import date


# ── helpers ──────────────────────────────────────────────────────────


def _seed_user_data(client, auth_header):
    """Create a representative set of user data across all tables."""
    # Category
    r = client.post("/categories", json={"name": "Food"}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    cat_id = r.get_json()[0]["id"]

    # Expense
    r = client.post(
        "/expenses",
        json={
            "amount": 42.50,
            "description": "Lunch",
            "category_id": cat_id,
            "date": "2026-03-01",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Recurring expense
    r = client.post(
        "/expenses/recurring",
        json={
            "amount": 100.0,
            "description": "Gym",
            "cadence": "MONTHLY",
            "start_date": "2026-01-01",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Bill
    r = client.post(
        "/bills",
        json={
            "name": "Internet",
            "amount": 49.99,
            "next_due_date": date.today().isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    # Reminder
    r = client.post(
        "/reminders",
        json={
            "message": "Pay rent",
            "send_at": "2026-04-01T09:00:00",
        },
        headers=auth_header,
    )
    assert r.status_code == 201

    return cat_id


def _register_and_login(client, email, password="password123"):
    """Register a new user and return (auth_header, access_token)."""
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code in (201, 409)
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}, token


# ── GET /pii/export ──────────────────────────────────────────────────


def test_export_returns_downloadable_json_with_all_tables(client, auth_header):
    _seed_user_data(client, auth_header)

    r = client.get("/pii/export", headers=auth_header)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert r.content_type.startswith("application/json")

    data = json.loads(r.data)
    assert "exported_at" in data
    assert "user" in data
    assert data["user"]["email"] == "test@example.com"
    assert len(data["categories"]) >= 1
    assert len(data["expenses"]) >= 1
    assert len(data["recurring_expenses"]) >= 1
    assert len(data["bills"]) >= 1
    assert len(data["reminders"]) >= 1
    assert "subscriptions" in data
    assert "audit_log" in data


def test_export_creates_audit_log_entry(client, auth_header):
    client.get("/pii/export", headers=auth_header)

    r = client.get("/pii/audit-log", headers=auth_header)
    assert r.status_code == 200
    actions = [e["action"] for e in r.get_json()]
    assert "PII_EXPORT" in actions


def test_export_empty_user_returns_valid_json(client, auth_header):
    """A user with no data should still get a valid export."""
    r = client.get("/pii/export", headers=auth_header)
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["user"]["email"] == "test@example.com"
    assert data["categories"] == []
    assert data["expenses"] == []


def test_export_requires_auth(client):
    r = client.get("/pii/export")
    assert r.status_code == 401


# ── POST /pii/delete ─────────────────────────────────────────────────


def test_delete_requires_confirmation_phrase(client, auth_header):
    r = client.post("/pii/delete", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "confirmation required" in r.get_json()["error"]


def test_delete_rejects_wrong_confirmation(client, auth_header):
    r = client.post(
        "/pii/delete", json={"confirm": "WRONG"}, headers=auth_header
    )
    assert r.status_code == 400


def test_delete_removes_all_user_data(client, auth_header):
    _seed_user_data(client, auth_header)

    # Verify data exists before delete
    r = client.get("/expenses", headers=auth_header)
    assert r.status_code == 200
    assert len(r.get_json()) >= 1

    # Perform delete
    r = client.post(
        "/pii/delete",
        json={"confirm": "DELETE_MY_DATA"},
        headers=auth_header,
    )
    assert r.status_code == 200
    assert "permanently deleted" in r.get_json()["message"]

    # Token should now be invalid (user gone)
    r = client.get("/auth/me", headers=auth_header)
    # Could be 401 (blocked JWT) or 404 (user not found)
    assert r.status_code in (401, 404)


def test_delete_is_complete_across_all_tables(client, app_fixture):
    """Register fresh user, seed data, delete, then verify every table
    is cleaned for that user."""
    with app_fixture.test_client() as c:
        header, _ = _register_and_login(c, "disposable@example.com")
        _seed_user_data(c, header)

        r = c.post(
            "/pii/delete",
            json={"confirm": "DELETE_MY_DATA"},
            headers=header,
        )
        assert r.status_code == 200

    # Check in a fresh app context that no rows remain for the deleted user.
    from app.models import (
        User,
        Category,
        Expense,
        RecurringExpense,
        Bill,
        Reminder,
        AdImpression,
        UserSubscription,
    )
    from app.extensions import db as _db

    with app_fixture.app_context():
        u = _db.session.query(User).filter_by(email="disposable@example.com").first()
        assert u is None, "User row should be deleted"


def test_delete_preserves_audit_trail(client, app_fixture):
    """After deletion the audit_log entries survive with user_id=NULL."""
    from app.models import AuditLog
    from app.extensions import db as _db

    with app_fixture.test_client() as c:
        header, _ = _register_and_login(c, "audit-trail@example.com")
        # Trigger an export to create an audit entry
        c.get("/pii/export", headers=header)
        # Delete
        c.post(
            "/pii/delete",
            json={"confirm": "DELETE_MY_DATA"},
            headers=header,
        )

    with app_fixture.app_context():
        entries = (
            _db.session.query(AuditLog)
            .filter(AuditLog.action.in_(["PII_EXPORT", "PII_DELETE"]))
            .filter(AuditLog.user_id.is_(None))
            .all()
        )
        actions = {e.action for e in entries}
        assert "PII_EXPORT" in actions
        assert "PII_DELETE" in actions


def test_delete_requires_auth(client):
    r = client.post("/pii/delete", json={"confirm": "DELETE_MY_DATA"})
    assert r.status_code == 401


def test_delete_without_body_returns_400(client, auth_header):
    r = client.post("/pii/delete", headers=auth_header)
    assert r.status_code == 400


# ── GET /pii/audit-log ───────────────────────────────────────────────


def test_audit_log_returns_entries(client, auth_header):
    # Trigger an export to generate an audit entry
    client.get("/pii/export", headers=auth_header)

    r = client.get("/pii/audit-log", headers=auth_header)
    assert r.status_code == 200
    entries = r.get_json()
    assert isinstance(entries, list)
    assert len(entries) >= 1
    assert entries[0]["action"] == "PII_EXPORT"
    assert "created_at" in entries[0]


def test_audit_log_requires_auth(client):
    r = client.get("/pii/audit-log")
    assert r.status_code == 401


def test_audit_log_records_own_view(client, auth_header):
    """Viewing the audit log itself should be recorded."""
    client.get("/pii/audit-log", headers=auth_header)
    r = client.get("/pii/audit-log", headers=auth_header)
    assert r.status_code == 200
    actions = [e["action"] for e in r.get_json()]
    assert "PII_AUDIT_LOG_VIEW" in actions


# ── isolation ────────────────────────────────────────────────────────


def test_export_only_returns_own_data(client, app_fixture):
    """User A's export must not contain User B's data."""
    with app_fixture.test_client() as c:
        header_a, _ = _register_and_login(c, "a@example.com")
        header_b, _ = _register_and_login(c, "b@example.com")

        # Create data for each
        c.post(
            "/expenses",
            json={"amount": 10, "description": "A-expense", "date": "2026-01-01"},
            headers=header_a,
        )
        c.post(
            "/expenses",
            json={"amount": 20, "description": "B-expense", "date": "2026-01-01"},
            headers=header_b,
        )

        # Export A
        r = c.get("/pii/export", headers=header_a)
        data = json.loads(r.data)
        descriptions = [e["notes"] for e in data["expenses"]]
        assert "A-expense" in descriptions
        assert "B-expense" not in descriptions

        # Export B
        r = c.get("/pii/export", headers=header_b)
        data = json.loads(r.data)
        descriptions = [e["notes"] for e in data["expenses"]]
        assert "B-expense" in descriptions
        assert "A-expense" not in descriptions


def test_delete_does_not_affect_other_users(client, app_fixture):
    """Deleting User A should leave User B's data intact."""
    with app_fixture.test_client() as c:
        header_a, _ = _register_and_login(c, "delete-a@example.com")
        header_b, _ = _register_and_login(c, "delete-b@example.com")

        c.post(
            "/expenses",
            json={"amount": 10, "description": "A-only", "date": "2026-01-01"},
            headers=header_a,
        )
        c.post(
            "/expenses",
            json={"amount": 20, "description": "B-only", "date": "2026-01-01"},
            headers=header_b,
        )

        # Delete A
        c.post(
            "/pii/delete",
            json={"confirm": "DELETE_MY_DATA"},
            headers=header_a,
        )

        # B's data should be intact
        r = c.get("/expenses", headers=header_b)
        assert r.status_code == 200
        descriptions = [e["description"] for e in r.get_json()]
        assert "B-only" in descriptions
