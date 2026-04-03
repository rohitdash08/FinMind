"""Tests for secure backup & encrypted export (issue #126)."""

from datetime import date
import json
import pytest


def _seed(client, auth_header):
    client.post("/expenses", json={"amount": 42, "description": "Test", "date": date.today().isoformat()}, headers=auth_header)


def test_export_json(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/export?format=json", headers=auth_header)
    assert resp.status_code == 200
    data = resp.get_json()
    assert "data" in data
    parsed = json.loads(data["data"])
    assert parsed["totals"]["expenses"] >= 1


def test_export_csv(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/export?format=csv", headers=auth_header)
    assert resp.status_code == 200
    assert "text/csv" in resp.content_type
    assert "id,amount" in resp.data.decode()


def test_encrypted_export_and_decrypt(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/export?format=json&encrypted=true&passphrase=mysecurepass123", headers=auth_header)
    assert resp.status_code == 200
    enc = resp.get_json()
    assert "ciphertext" in enc
    assert enc["algorithm"] == "AES-256-GCM"

    # Decrypt
    enc["passphrase"] = "mysecurepass123"
    resp2 = client.post("/export/decrypt", json=enc, headers=auth_header)
    assert resp2.status_code == 200
    plaintext = resp2.get_json()["data"]
    parsed = json.loads(plaintext)
    assert parsed["totals"]["expenses"] >= 1


def test_wrong_passphrase(client, auth_header):
    _seed(client, auth_header)
    resp = client.get("/export?encrypted=true&passphrase=correctpass1", headers=auth_header)
    enc = resp.get_json()
    enc["passphrase"] = "wrongpassword"
    resp2 = client.post("/export/decrypt", json=enc, headers=auth_header)
    assert resp2.status_code == 400


def test_short_passphrase_rejected(client, auth_header):
    resp = client.get("/export?encrypted=true&passphrase=short", headers=auth_header)
    assert resp.status_code == 400


def test_missing_passphrase(client, auth_header):
    resp = client.get("/export?encrypted=true", headers=auth_header)
    assert resp.status_code == 400
