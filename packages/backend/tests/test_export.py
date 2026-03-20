"""Tests for the encrypted export endpoint (Issue #126)."""

import base64
import json
from datetime import date

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


def _decrypt(payload: dict, password: str) -> bytes:
    salt = base64.b64decode(payload["salt"])
    nonce = base64.b64decode(payload["nonce"])
    ciphertext = base64.b64decode(payload["ciphertext"])
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=payload["iterations"],
    )
    key = kdf.derive(password.encode("utf-8"))
    return AESGCM(key).decrypt(nonce, ciphertext, None)


def test_export_json_encrypted(client, auth_header):
    # Seed data
    client.post("/categories", json={"name": "Food"}, headers=auth_header)
    client.post(
        "/expenses",
        json={"amount": 100, "description": "Lunch", "date": date.today().isoformat()},
        headers=auth_header,
    )

    password = "my-secure-password-123"
    r = client.post(
        "/export",
        json={"password": password, "format": "json"},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["algorithm"] == "AES-256-GCM"
    assert body["format"] == "json"

    # Decrypt and verify
    plaintext = _decrypt(body, password)
    data = json.loads(plaintext)
    assert "expenses" in data
    assert "categories" in data
    assert "bills" in data
    assert len(data["expenses"]) >= 1
    assert data["expenses"][0]["description"] == "Lunch"


def test_export_csv_encrypted(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 50, "description": "Coffee", "date": date.today().isoformat()},
        headers=auth_header,
    )

    password = "another-password-456"
    r = client.post(
        "/export",
        json={"password": password, "format": "csv"},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()
    assert body["format"] == "csv"

    plaintext = _decrypt(body, password).decode("utf-8")
    assert "[expenses]" in plaintext
    assert "Coffee" in plaintext


def test_export_rejects_short_password(client, auth_header):
    r = client.post(
        "/export",
        json={"password": "short", "format": "json"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "password" in r.get_json()["error"].lower()


def test_export_rejects_invalid_format(client, auth_header):
    r = client.post(
        "/export",
        json={"password": "long-enough-password", "format": "xml"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "format" in r.get_json()["error"].lower()


def test_export_requires_auth(client):
    r = client.post("/export", json={"password": "test-password-123", "format": "json"})
    assert r.status_code == 401


def test_export_wrong_password_fails_decrypt(client, auth_header):
    client.post(
        "/expenses",
        json={"amount": 10, "description": "Test", "date": date.today().isoformat()},
        headers=auth_header,
    )
    r = client.post(
        "/export",
        json={"password": "correct-password-123", "format": "json"},
        headers=auth_header,
    )
    assert r.status_code == 200
    body = r.get_json()

    import pytest
    with pytest.raises(Exception):
        _decrypt(body, "wrong-password-999")
