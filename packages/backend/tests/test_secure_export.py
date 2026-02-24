"""Tests for secure backup and encrypted export (issue #126)."""
import io
import json
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.extensions import db as _db
from app.models import Category, Expense, User
from app.services.export import (
    _collect_user_data,
    decrypt_payload,
    encrypt_payload,
    export_user_csv_zip,
    export_user_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_data(app_fixture):
    """Seed a fresh user + category + expense inside the app context."""
    with app_fixture.app_context():
        user = User(
            email="export@example.com",
            password_hash="x",
            preferred_currency="INR",
        )
        _db.session.add(user)
        _db.session.flush()

        cat = Category(user_id=user.id, name="Food")
        _db.session.add(cat)
        _db.session.flush()

        _db.session.add(
            Expense(
                user_id=user.id,
                category_id=cat.id,
                amount=Decimal("1500"),
                currency="INR",
                expense_type="EXPENSE",
                spent_at=date(2026, 2, 1),
            )
        )
        _db.session.commit()
        return user.id


# ---------------------------------------------------------------------------
# _collect_user_data
# ---------------------------------------------------------------------------


class TestCollectUserData:
    def test_returns_expected_keys(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            data = _collect_user_data(uid, _db.session)
        for key in ("user", "categories", "expenses", "bills", "reminders"):
            assert key in data

    def test_expenses_populated(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            data = _collect_user_data(uid, _db.session)
        assert len(data["expenses"]) == 1
        assert data["expenses"][0]["currency"] == "INR"

    def test_unknown_user_returns_empty(self, app_fixture):
        with app_fixture.app_context():
            data = _collect_user_data(99999, _db.session)
        assert data == {}

    def test_export_version_present(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            data = _collect_user_data(uid, _db.session)
        assert data["export_version"] == "1.0"


# ---------------------------------------------------------------------------
# export_user_json
# ---------------------------------------------------------------------------


class TestExportJson:
    def test_returns_valid_json(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_json(uid, _db.session)
        data = json.loads(raw)
        assert "expenses" in data
        assert data["export_version"] == "1.0"

    def test_output_is_bytes(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_json(uid, _db.session)
        assert isinstance(raw, bytes)

    def test_contains_user_email(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_json(uid, _db.session)
        data = json.loads(raw)
        assert data["user"]["email"] == "export@example.com"


# ---------------------------------------------------------------------------
# export_user_csv_zip
# ---------------------------------------------------------------------------


class TestExportCsvZip:
    def test_returns_valid_zip(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_csv_zip(uid, _db.session)
        assert zipfile.is_zipfile(io.BytesIO(raw))

    def test_zip_contains_expenses_csv(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_csv_zip(uid, _db.session)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
        assert "expenses.csv" in names

    def test_csv_has_header_row(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_csv_zip(uid, _db.session)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_content = zf.read("expenses.csv").decode("utf-8")
        assert "amount" in csv_content
        assert "currency" in csv_content

    def test_categories_csv_present(self, app_fixture):
        uid = _seed_data(app_fixture)
        with app_fixture.app_context():
            raw = export_user_csv_zip(uid, _db.session)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
        assert "categories.csv" in names


# ---------------------------------------------------------------------------
# encrypt / decrypt
# ---------------------------------------------------------------------------


class TestEncryptDecrypt:
    def test_encrypt_returns_bytes(self):
        result = encrypt_payload(b"hello world", "my-passphrase")
        assert isinstance(result, bytes)

    def test_decrypt_roundtrip(self):
        original = b"sensitive financial data"
        passphrase = "s3cur3P@ssw0rd"
        encrypted = encrypt_payload(original, passphrase)
        decrypted = decrypt_payload(encrypted, passphrase)
        assert decrypted == original

    def test_wrong_passphrase_raises(self):
        encrypted = encrypt_payload(b"data", "correct")
        with pytest.raises(Exception):  # cryptography.fernet.InvalidToken
            decrypt_payload(encrypted, "wrong")

    def test_different_encryptions_different_output(self):
        # Random salt → two encryptions of same data differ
        enc1 = encrypt_payload(b"same data", "passphrase")
        enc2 = encrypt_payload(b"same data", "passphrase")
        assert enc1 != enc2

    def test_large_payload(self):
        big = b"x" * 100_000
        enc = encrypt_payload(big, "pass")
        dec = decrypt_payload(enc, "pass")
        assert dec == big


# ---------------------------------------------------------------------------
# Export endpoints (HTTP-level)
# ---------------------------------------------------------------------------


class TestExportEndpoints:
    def test_json_requires_auth(self, client):
        resp = client.get("/export/json")
        assert resp.status_code in (401, 422)

    def test_csv_requires_auth(self, client):
        resp = client.get("/export/csv")
        assert resp.status_code in (401, 422)

    def test_json_endpoint_exists(self, client):
        # Must be 401/422 (auth required), not 404
        assert client.get("/export/json").status_code != 404

    def test_csv_endpoint_exists(self, client):
        assert client.get("/export/csv").status_code != 404

    def test_json_export_returns_file(self, client, auth_header):
        resp = client.get("/export/json", headers=auth_header)
        assert resp.status_code == 200
        assert resp.content_type == "application/json"
        assert b"export_version" in resp.data

    def test_csv_export_returns_zip(self, client, auth_header):
        resp = client.get("/export/csv", headers=auth_header)
        assert resp.status_code == 200
        assert resp.content_type == "application/zip"
        assert zipfile.is_zipfile(io.BytesIO(resp.data))

    def test_json_encrypted_missing_passphrase_returns_400(self, client, auth_header):
        resp = client.get("/export/json?encrypted=true", headers=auth_header)
        assert resp.status_code == 400
        assert "passphrase" in resp.get_json().get("error", "")

    def test_csv_encrypted_missing_passphrase_returns_400(self, client, auth_header):
        resp = client.get("/export/csv?encrypted=true", headers=auth_header)
        assert resp.status_code == 400

    def test_json_encrypted_download(self, client, auth_header):
        resp = client.get(
            "/export/json?encrypted=true&passphrase=testpass", headers=auth_header
        )
        assert resp.status_code == 200
        assert resp.content_type == "application/octet-stream"
        # Verify it's valid base64 encrypted payload
        decrypted = decrypt_payload(resp.data, "testpass")
        data = json.loads(decrypted)
        assert "export_version" in data

    def test_csv_encrypted_download(self, client, auth_header):
        resp = client.get(
            "/export/csv?encrypted=true&passphrase=testpass", headers=auth_header
        )
        assert resp.status_code == 200
        assert resp.content_type == "application/octet-stream"
        decrypted = decrypt_payload(resp.data, "testpass")
        assert zipfile.is_zipfile(io.BytesIO(decrypted))

    def test_json_content_disposition_header(self, client, auth_header):
        resp = client.get("/export/json", headers=auth_header)
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert ".json" in resp.headers.get("Content-Disposition", "")
