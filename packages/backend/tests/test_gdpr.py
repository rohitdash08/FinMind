"""Tests for GDPR PII export and delete workflow."""


def _auth_header(client):
    email = "gdpr@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


def test_export_data(client):
    headers = _auth_header(client)
    r = client.post("/gdpr/export", headers=headers)
    assert r.status_code == 200
    export = r.get_json()["export"]
    assert "user" in export
    assert export["user"]["email"] == "gdpr@test.com"
    assert "expenses" in export
    assert "categories" in export
    assert "bills" in export


def test_data_status(client):
    headers = _auth_header(client)
    r = client.get("/gdpr/status", headers=headers)
    assert r.status_code == 200
    summary = r.get_json()["data_summary"]
    assert "expenses" in summary
    assert "bills" in summary


def test_delete_requires_confirmation(client):
    headers = _auth_header(client)
    r = client.post("/gdpr/delete", json={}, headers=headers)
    assert r.status_code == 400
    assert "confirm" in r.get_json()["error"]


def test_delete_with_confirmation(client):
    # Create a fresh user for deletion
    email = "deleteme@test.com"
    password = "secret123"
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    headers = {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    r = client.post("/gdpr/delete", json={"confirm": "DELETE_MY_DATA"}, headers=headers)
    assert r.status_code == 200
    assert "permanently deleted" in r.get_json()["message"]

    # Verify user can no longer access API
    r = client.get("/gdpr/status", headers=headers)
    # Token still valid but user gone - should get 404 or similar
    assert r.status_code in (401, 404, 422)
