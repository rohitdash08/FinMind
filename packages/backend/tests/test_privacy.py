from datetime import date


def _auth(client, email="privacy@test.com", password="secret123"):
    """Register + login and return auth header."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed_data(client, auth):
    """Create some sample data for export tests."""
    client.post(
        "/categories",
        json={"name": "Food"},
        headers=auth,
    )
    client.post(
        "/expenses",
        json={"amount": 42.50, "description": "Lunch", "date": "2025-01-15"},
        headers=auth,
    )


def test_export_returns_all_user_data(client):
    auth = _auth(client)
    _seed_data(client, auth)

    r = client.get("/privacy/export", headers=auth)
    assert r.status_code == 200
    data = r.get_json()

    assert "profile" in data
    assert data["profile"]["email"] == "privacy@test.com"
    assert "exported_at" in data
    assert isinstance(data["expenses"], list)
    assert isinstance(data["categories"], list)
    assert isinstance(data["bills"], list)
    assert isinstance(data["reminders"], list)
    assert isinstance(data["recurring_expenses"], list)
    assert isinstance(data["subscriptions"], list)


def test_export_creates_audit_log(client):
    auth = _auth(client)
    client.get("/privacy/export", headers=auth)

    r = client.get("/privacy/audit-log", headers=auth)
    assert r.status_code == 200
    logs = r.get_json()
    assert any(log["action"] == "pii_export" for log in logs)


def test_delete_request_and_cancel(client):
    auth = _auth(client)

    # Request deletion
    r = client.post("/privacy/delete-request", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["grace_period_days"] == 30
    assert "deletion_scheduled_for" in data

    # Check status
    r = client.get("/privacy/deletion-status", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["pending"] is True

    # Duplicate request should fail
    r = client.post("/privacy/delete-request", headers=auth)
    assert r.status_code == 409

    # Cancel
    r = client.post("/privacy/delete-cancel", headers=auth)
    assert r.status_code == 200

    # Status should be cleared
    r = client.get("/privacy/deletion-status", headers=auth)
    assert r.get_json()["pending"] is False


def test_delete_cancel_without_request(client):
    auth = _auth(client)
    r = client.post("/privacy/delete-cancel", headers=auth)
    assert r.status_code == 400


def test_delete_confirm_removes_all_data(client):
    auth = _auth(client, email="doomed@test.com")
    _seed_data(client, auth)

    # Must request first
    r = client.post("/privacy/delete-confirm", headers=auth)
    assert r.status_code == 400

    # Request then confirm
    client.post("/privacy/delete-request", headers=auth)
    r = client.post("/privacy/delete-confirm", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["message"] == "account permanently deleted"

    # Token should no longer work (user gone)
    r = client.get("/privacy/export", headers=auth)
    assert r.status_code == 404


def test_delete_confirm_preserves_audit_logs(client, app_fixture):
    auth = _auth(client, email="audit@test.com")
    client.post("/privacy/delete-request", headers=auth)
    client.post("/privacy/delete-confirm", headers=auth)

    # Audit logs should still exist with user_id=NULL
    from app.models import AuditLog
    from app.extensions import db

    with app_fixture.app_context():
        logs = (
            db.session.query(AuditLog)
            .filter(AuditLog.action.in_(["deletion_requested", "deletion_confirmed"]))
            .all()
        )
        assert len(logs) >= 2
        for log in logs:
            assert log.user_id is None


def test_audit_log_records_ip_and_action(client):
    auth = _auth(client, email="auditip@test.com")
    client.get("/privacy/export", headers=auth)

    r = client.get("/privacy/audit-log", headers=auth)
    logs = r.get_json()
    assert len(logs) >= 1
    assert logs[0]["action"] == "pii_export"
    assert "ip_address" in logs[0]


def test_deletion_status_no_request(client):
    auth = _auth(client, email="nostatus@test.com")
    r = client.get("/privacy/deletion-status", headers=auth)
    assert r.status_code == 200
    assert r.get_json()["pending"] is False
