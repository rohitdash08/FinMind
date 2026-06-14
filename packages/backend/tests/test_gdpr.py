"""
Tests for GDPR PII Export & Delete endpoints.

Covers:
- JSON export (GET /gdpr/export)
- CSV export  (GET /gdpr/export/csv)
- Delete initiation (POST /gdpr/delete)
- Audit trail    (GET /gdpr/audit)
- Hard-delete blocked before grace period (POST /gdpr/delete/confirm)
"""


GDPR_EMAIL = "gdpr_user@test.com"
GDPR_PASSWORD = "gdpr_secret99"


def _register_and_login(client, email=GDPR_EMAIL, password=GDPR_PASSWORD):
    """Helper: register (idempotent) and return access_token."""
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    return r.get_json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ── Export tests ───────────────────────────────────────────────────────────────


def test_gdpr_export_json_structure(client):
    token = _register_and_login(client)
    r = client.get("/gdpr/export", headers=_auth(token))
    assert r.status_code == 200
    assert r.content_type.startswith("application/json")

    data = r.get_json()
    assert "profile" in data
    assert data["profile"]["email"] == GDPR_EMAIL
    assert "expenses" in data
    assert "categories" in data
    assert "bills" in data
    assert "reminders" in data
    assert "recurring_expenses" in data
    assert "subscriptions" in data
    assert "exported_at" in data


def test_gdpr_export_requires_auth(client):
    r = client.get("/gdpr/export")
    assert r.status_code == 401


def test_gdpr_export_csv(client):
    token = _register_and_login(client, "gdpr_csv@test.com", GDPR_PASSWORD)
    r = client.get("/gdpr/export/csv", headers=_auth(token))
    assert r.status_code == 200
    assert "text/csv" in r.content_type
    body = r.get_data(as_text=True)
    # Must have CSV header row
    assert "amount" in body and "currency" in body


def test_gdpr_export_csv_requires_auth(client):
    r = client.get("/gdpr/export/csv")
    assert r.status_code == 401


# ── Delete initiation tests ────────────────────────────────────────────────────


def test_gdpr_delete_initiate_requires_password(client):
    token = _register_and_login(client, "gdpr_del1@test.com", GDPR_PASSWORD)
    # No password in body
    r = client.post("/gdpr/delete", headers=_auth(token), json={})
    assert r.status_code == 400


def test_gdpr_delete_initiate_wrong_password(client):
    token = _register_and_login(client, "gdpr_del2@test.com", GDPR_PASSWORD)
    r = client.post(
        "/gdpr/delete",
        headers=_auth(token),
        json={"password": "wrong_password"},
    )
    assert r.status_code == 401


def test_gdpr_delete_initiate_success(client):
    token = _register_and_login(client, "gdpr_del3@test.com", GDPR_PASSWORD)
    r = client.post(
        "/gdpr/delete",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD},
    )
    assert r.status_code == 202
    data = r.get_json()
    assert "scheduled_deletion_at" in data
    assert "grace_period_days" in data
    assert data["grace_period_days"] == 30


def test_gdpr_delete_initiate_idempotent(client):
    """A second initiation request while grace period is active returns 409."""
    token = _register_and_login(client, "gdpr_del4@test.com", GDPR_PASSWORD)
    payload = {"password": GDPR_PASSWORD}
    r1 = client.post("/gdpr/delete", headers=_auth(token), json=payload)
    assert r1.status_code == 202

    r2 = client.post("/gdpr/delete", headers=_auth(token), json=payload)
    assert r2.status_code == 409


# ── Hard-delete tests ──────────────────────────────────────────────────────────


def test_gdpr_delete_confirm_blocked_before_grace_period(client):
    """Hard delete should be blocked if grace period has not elapsed."""
    token = _register_and_login(client, "gdpr_del5@test.com", GDPR_PASSWORD)
    # Initiate first
    client.post(
        "/gdpr/delete",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD},
    )
    # Attempt immediate hard delete — must be blocked
    r = client.post(
        "/gdpr/delete/confirm",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD, "confirm": True},
    )
    assert r.status_code == 403
    data = r.get_json()
    assert "days_remaining" in data


def test_gdpr_delete_confirm_requires_confirm_flag(client):
    token = _register_and_login(client, "gdpr_del6@test.com", GDPR_PASSWORD)
    r = client.post(
        "/gdpr/delete/confirm",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD},  # missing confirm
    )
    assert r.status_code == 400


def test_gdpr_delete_confirm_requires_prior_initiation(client):
    """Hard delete without prior initiation should fail with 409."""
    token = _register_and_login(client, "gdpr_del7@test.com", GDPR_PASSWORD)
    r = client.post(
        "/gdpr/delete/confirm",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD, "confirm": True},
    )
    assert r.status_code == 409


# ── Audit trail tests ──────────────────────────────────────────────────────────


def test_gdpr_audit_trail(client):
    token = _register_and_login(client, "gdpr_audit@test.com", GDPR_PASSWORD)
    # Generate some audit records
    client.get("/gdpr/export", headers=_auth(token))
    client.post(
        "/gdpr/delete",
        headers=_auth(token),
        json={"password": GDPR_PASSWORD},
    )

    r = client.get("/gdpr/audit", headers=_auth(token))
    assert r.status_code == 200
    logs = r.get_json()
    assert isinstance(logs, list)
    assert len(logs) >= 2
    actions = [log["action"] for log in logs]
    assert any("GDPR_EXPORT" in a for a in actions)
    assert any("GDPR_DELETE_INITIATED" in a for a in actions)


def test_gdpr_audit_requires_auth(client):
    r = client.get("/gdpr/audit")
    assert r.status_code == 401
