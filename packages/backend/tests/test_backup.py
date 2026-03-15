"""Tests for secure backup & encrypted export functionality."""

import json
import base64
import pytest
from app.services.backup import (
    encrypt_data,
    decrypt_data,
    derive_key,
    export_to_json,
    export_to_csv,
    encrypt_export,
    decrypt_export,
    DecryptionError,
    _serialize_value,
)
from decimal import Decimal
from datetime import date, datetime


# ── Unit tests for encryption ──────────────────────────────────────────────


class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        plaintext = b"Hello, FinMind backup!"
        passphrase = "strong-passphrase-123"
        encrypted = encrypt_data(plaintext, passphrase)
        decrypted = decrypt_data(encrypted, passphrase)
        assert decrypted == plaintext

    def test_encrypt_produces_different_ciphertext(self):
        """Same plaintext + passphrase should produce different ciphertext (random salt/nonce)."""
        plaintext = b"identical data"
        passphrase = "same-passphrase"
        enc1 = encrypt_data(plaintext, passphrase)
        enc2 = encrypt_data(plaintext, passphrase)
        assert enc1 != enc2  # Different salt/nonce
        # But both decrypt to the same value
        assert decrypt_data(enc1, passphrase) == plaintext
        assert decrypt_data(enc2, passphrase) == plaintext

    def test_wrong_passphrase_raises(self):
        plaintext = b"secret data"
        encrypted = encrypt_data(plaintext, "correct-pass")
        with pytest.raises(DecryptionError):
            decrypt_data(encrypted, "wrong-passphrase")

    def test_truncated_data_raises(self):
        with pytest.raises(DecryptionError):
            decrypt_data(b"short", "any-passphrase")

    def test_tampered_ciphertext_raises(self):
        plaintext = b"tamper test"
        encrypted = encrypt_data(plaintext, "passphrase123")
        # Flip a byte in the ciphertext portion (after salt + nonce)
        tampered = bytearray(encrypted)
        tampered[30] ^= 0xFF
        with pytest.raises(DecryptionError):
            decrypt_data(bytes(tampered), "passphrase123")

    def test_key_derivation_deterministic(self):
        salt = b"\x00" * 16
        key1, _ = derive_key("test-pass", salt)
        key2, _ = derive_key("test-pass", salt)
        assert key1 == key2
        assert len(key1) == 32


# ── Unit tests for serialization ───────────────────────────────────────────


class TestSerialization:
    def test_decimal_serialization(self):
        assert _serialize_value(Decimal("42.50")) == 42.5

    def test_date_serialization(self):
        d = date(2026, 3, 15)
        assert _serialize_value(d) == "2026-03-15"

    def test_datetime_serialization(self):
        dt = datetime(2026, 3, 15, 10, 30, 0)
        assert _serialize_value(dt) == "2026-03-15T10:30:00"

    def test_passthrough(self):
        assert _serialize_value("hello") == "hello"
        assert _serialize_value(42) == 42
        assert _serialize_value(None) is None


# ── Unit tests for export formats ──────────────────────────────────────────


class TestExportFormats:
    def _sample_data(self):
        return {
            "user": [
                {
                    "id": 1,
                    "email": "test@example.com",
                    "preferred_currency": "USD",
                    "role": "USER",
                    "created_at": "2026-01-01T00:00:00",
                }
            ],
            "expenses": [
                {
                    "id": 1,
                    "category_id": 1,
                    "amount": 42.5,
                    "currency": "USD",
                    "expense_type": "EXPENSE",
                    "notes": "Groceries",
                    "spent_at": "2026-03-14",
                    "created_at": "2026-03-14T12:00:00",
                },
                {
                    "id": 2,
                    "category_id": 2,
                    "amount": 150.0,
                    "currency": "USD",
                    "expense_type": "EXPENSE",
                    "notes": "Rent",
                    "spent_at": "2026-03-01",
                    "created_at": "2026-03-01T00:00:00",
                },
            ],
        }

    def test_json_export_structure(self):
        data = self._sample_data()
        result = export_to_json(data)
        parsed = json.loads(result)

        assert "metadata" in parsed
        assert "data" in parsed
        assert parsed["metadata"]["version"] == "1.0"
        assert parsed["metadata"]["format"] == "finmind_backup"
        assert parsed["metadata"]["record_count"]["user"] == 1
        assert parsed["metadata"]["record_count"]["expenses"] == 2
        assert len(parsed["data"]["expenses"]) == 2

    def test_csv_export_structure(self):
        data = self._sample_data()
        result = export_to_csv(data)

        assert "=== user ===" in result
        assert "=== expenses ===" in result
        assert "test@example.com" in result
        assert "Groceries" in result

    def test_csv_empty_table(self):
        data = {"categories": []}
        result = export_to_csv(data)
        assert "=== categories ===" in result

    def test_json_empty_data(self):
        data = {}
        result = export_to_json(data)
        parsed = json.loads(result)
        assert parsed["metadata"]["record_count"] == {}


# ── Integration tests for encrypt/decrypt export ───────────────────────────


class TestEncryptDecryptExport:
    def test_encrypt_decrypt_export_roundtrip(self):
        sample = json.dumps({"key": "value", "number": 42})
        result = encrypt_export(sample, "my-passphrase-123")

        assert "encrypted_data" in result
        assert result["format"] == "aes-256-gcm"

        # Verify encrypted_data is valid base64
        raw = base64.b64decode(result["encrypted_data"])
        assert len(raw) > 28  # salt + nonce + tag minimum

        # Decrypt
        decrypted = decrypt_export(result["encrypted_data"], "my-passphrase-123")
        assert decrypted == sample

    def test_wrong_passphrase_on_export(self):
        sample = json.dumps({"data": "test"})
        result = encrypt_export(sample, "correct-pass")

        with pytest.raises(DecryptionError):
            decrypt_export(result["encrypted_data"], "wrong-pass")


# ── API route tests ────────────────────────────────────────────────────────


class TestBackupRoutes:
    @pytest.fixture
    def client(self, app_fixture):
        return app_fixture.test_client()

    @pytest.fixture
    def auth_headers(self, client):
        """Register + login a test user, return auth headers."""
        client.post(
            "/auth/register",
            json={
                "email": "backup_test@example.com",
                "password": "TestPass123!",
            },
        )
        resp = client.post(
            "/auth/login",
            json={
                "email": "backup_test@example.com",
                "password": "TestPass123!",
            },
        )
        data = resp.get_json()
        token = data.get("access_token") or data.get("token") or ""
        return {"Authorization": f"Bearer {token}"}

    def test_export_summary_no_auth(self, client):
        resp = client.get("/backup/export/summary")
        assert resp.status_code == 401

    def test_export_summary(self, client, auth_headers):
        resp = client.get("/backup/export/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "summary" in data

    def test_export_json(self, client, auth_headers):
        resp = client.get("/backup/export?format=json", headers=auth_headers)
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        body = json.loads(resp.data)
        assert "metadata" in body
        assert "data" in body

    def test_export_invalid_format(self, client, auth_headers):
        resp = client.get("/backup/export?format=xml", headers=auth_headers)
        assert resp.status_code == 400

    def test_export_encrypted_without_passphrase(self, client, auth_headers):
        resp = client.get(
            "/backup/export?format=json&encrypt=true", headers=auth_headers
        )
        assert resp.status_code == 400

    def test_export_encrypted(self, client, auth_headers):
        headers = {
            **auth_headers,
            "X-Backup-Passphrase": "test-passphrase-12345",
        }
        resp = client.get(
            "/backup/export?format=json&encrypt=true", headers=headers
        )
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert "encrypted_data" in body

    def test_export_encrypted_short_passphrase(self, client, auth_headers):
        headers = {
            **auth_headers,
            "X-Backup-Passphrase": "short",
        }
        resp = client.get(
            "/backup/export?format=json&encrypt=true", headers=headers
        )
        assert resp.status_code == 400

    def test_decrypt_wrong_data(self, client, auth_headers):
        resp = client.post(
            "/backup/decrypt",
            json={"encrypted_data": "dGhpcyBpcyBub3QgZW5jcnlwdGVk", "passphrase": "wrong"},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_decrypt_missing_fields(self, client, auth_headers):
        resp = client.post(
            "/backup/decrypt",
            json={"encrypted_data": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 400
