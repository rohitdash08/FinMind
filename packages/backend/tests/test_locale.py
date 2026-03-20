"""Tests for locale preference on the User model and /auth/me endpoint."""


def _register_and_login(client, email="locale@test.com", password="secret123"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    access = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {access}"}


def test_me_returns_default_locale(client):
    auth = _register_and_login(client)
    r = client.get("/auth/me", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["locale"] == "en-US"


def test_update_locale(client):
    auth = _register_and_login(client, email="locale2@test.com")
    r = client.patch("/auth/me", json={"locale": "fr-FR"}, headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["locale"] == "fr-FR"

    # Verify persistence
    r = client.get("/auth/me", headers=auth)
    assert r.get_json()["locale"] == "fr-FR"


def test_update_locale_unsupported_returns_400(client):
    auth = _register_and_login(client, email="locale3@test.com")
    r = client.patch("/auth/me", json={"locale": "xx-YY"}, headers=auth)
    assert r.status_code == 400
    assert "unsupported locale" in r.get_json()["error"]


def test_update_locale_and_currency_together(client):
    auth = _register_and_login(client, email="locale4@test.com")
    r = client.patch(
        "/auth/me",
        json={"preferred_currency": "EUR", "locale": "de-DE"},
        headers=auth,
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["preferred_currency"] == "EUR"
    assert data["locale"] == "de-DE"


def test_update_currency_alone_preserves_locale(client):
    auth = _register_and_login(client, email="locale5@test.com")
    # Set locale first
    client.patch("/auth/me", json={"locale": "ja-JP"}, headers=auth)
    # Update only currency
    r = client.patch(
        "/auth/me", json={"preferred_currency": "JPY"}, headers=auth
    )
    assert r.status_code == 200
    data = r.get_json()
    assert data["preferred_currency"] == "JPY"
    assert data["locale"] == "ja-JP"
