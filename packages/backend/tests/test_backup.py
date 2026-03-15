"""Tests for secure backup and encrypted export."""

import base64
import hashlib
import json
from datetime import datetime, date, timedelta
from unittest.mock import patch

import pytest
from app.extensions import db


# ═══════════════════════════════════════════════════════════════════
# Service-level unit tests
# ═══════════════════════════════════════════════════════════════════


class TestEncryption:
    """Verify encrypt/decrypt round-trip."""

    def test_encrypt_decrypt_roundtrip(self, app_fixture):
        from app.services.backup import _encrypt_data, _decrypt_data, _generate_key

        key = _generate_key()
        plaintext = b"Hello, secure backup!"
        encrypted = _encrypt_data(plaintext, key)

        assert "iv" in encrypted
        assert "data" in encrypted
        assert "hmac" in encrypted
        assert encrypted["algorithm"] == "AES-256-SIM"

        decrypted = _decrypt_data(encrypted, key)
        assert decrypted == plaintext

    def test_wrong_key_fails_hmac(self, app_fixture):
        from app.services.backup import _encrypt_data, _decrypt_data, _generate_key

        key1 = _generate_key()
        key2 = _generate_key()
        encrypted = _encrypt_data(b"secret data", key1)

        with pytest.raises(ValueError, match="integrity"):
            _decrypt_data(encrypted, key2)

    def test_tampered_data_fails_hmac(self, app_fixture):
        from app.services.backup import _encrypt_data, _decrypt_data, _generate_key

        key = _generate_key()
        encrypted = _encrypt_data(b"original", key)
        # Tamper with encrypted data
        raw = base64.b64decode(encrypted["data"])
        tampered = bytes([b ^ 0xFF for b in raw])
        encrypted["data"] = base64.b64encode(tampered).decode()

        with pytest.raises(ValueError, match="integrity"):
            _decrypt_data(encrypted, key)

    def test_generate_key_length(self, app_fixture):
        from app.services.backup import _generate_key

        key = _generate_key()
        assert len(key) == 32  # 256 bits

    def test_generate_key_uniqueness(self, app_fixture):
        from app.services.backup import _generate_key

        keys = {_generate_key() for _ in range(50)}
        assert len(keys) == 50

    def test_encrypt_large_payload(self, app_fixture):
        from app.services.backup import _encrypt_data, _decrypt_data, _generate_key

        key = _generate_key()
        big = b"x" * 100_000
        encrypted = _encrypt_data(big, key)
        assert _decrypt_data(encrypted, key) == big


class TestDataCollection:
    """Test _collect_user_data."""

    def test_collect_all_sections(self, client, auth_header):
        from app.services.backup import _collect_user_data

        with client.application.app_context():
            data = _collect_user_data(1)
            assert "exported_at" in data
            assert "sections" in data
            # All 6 sections present
            assert "profile" in data["sections"]
            assert "categories" in data["sections"]
            assert "expenses" in data["sections"]
            assert "bills" in data["sections"]
            assert "reminders" in data["sections"]
            assert "recurring" in data["sections"]

    def test_collect_selective_sections(self, client, auth_header):
        from app.services.backup import _collect_user_data

        with client.application.app_context():
            data = _collect_user_data(1, sections=["profile", "expenses"])
            assert "profile" in data["sections"]
            assert "expenses" in data["sections"]
            assert "categories" not in data["sections"]
            assert "bills" not in data["sections"]

    def test_profile_section_content(self, client, auth_header):
        from app.services.backup import _collect_user_data

        with client.application.app_context():
            data = _collect_user_data(1)
            profile = data["sections"]["profile"]
            assert "email" in profile
            assert profile["email"] == "test@example.com"

    def test_expenses_section_with_data(self, client, auth_header):
        from app.services.backup import _collect_user_data
        from app.models import Category, Expense

        with client.application.app_context():
            cat = Category(user_id=1, name="Food")
            db.session.add(cat)
            db.session.flush()
            exp = Expense(
                user_id=1,
                amount=42.50,
                currency="USD",
                category_id=cat.id,
                expense_type="necessity",
                notes="lunch",
            )
            db.session.add(exp)
            db.session.commit()

            data = _collect_user_data(1)
            expenses = data["sections"]["expenses"]
            assert len(expenses) == 1
            assert expenses[0]["amount"] == 42.50
            assert expenses[0]["notes"] == "lunch"


class TestCsvConversion:
    """Test _data_to_csv."""

    def test_csv_output_contains_headers(self, app_fixture):
        from app.services.backup import _data_to_csv

        data = {
            "sections": {
                "categories": [
                    {"id": 1, "name": "Food", "created_at": "2026-01-01"},
                    {"id": 2, "name": "Travel", "created_at": "2026-02-01"},
                ],
            },
        }
        csv_str = _data_to_csv(data)
        assert "CATEGORIES" in csv_str
        assert "id" in csv_str
        assert "name" in csv_str
        assert "Food" in csv_str
        assert "Travel" in csv_str

    def test_csv_handles_dict_section(self, app_fixture):
        from app.services.backup import _data_to_csv

        data = {
            "sections": {
                "profile": {"email": "a@b.com", "currency": "USD"},
            },
        }
        csv_str = _data_to_csv(data)
        assert "PROFILE" in csv_str
        assert "a@b.com" in csv_str

    def test_csv_empty_sections(self, app_fixture):
        from app.services.backup import _data_to_csv

        data = {"sections": {}}
        csv_str = _data_to_csv(data)
        assert csv_str == ""


# ═══════════════════════════════════════════════════════════════════
# create_backup tests
# ═══════════════════════════════════════════════════════════════════


class TestCreateBackup:
    """Test the create_backup service function."""

    def test_full_json_encrypted(self, client, auth_header):
        from app.services.backup import create_backup

        with client.application.app_context():
            result = create_backup(1, backup_type="full", format="json", encrypt=True)

        assert result["backup_type"] == "full"
        assert result["format"] == "json"
        assert result["encrypted"] is True
        assert result["encryption_key"] is not None
        assert result["file_hash"]
        assert result["file_size"] > 0
        assert "backup_id" in result
        assert "data" in result
        # Data is encrypted
        assert "iv" in result["data"]
        assert "hmac" in result["data"]

    def test_full_json_unencrypted(self, client, auth_header):
        from app.services.backup import create_backup

        with client.application.app_context():
            result = create_backup(1, backup_type="full", format="json", encrypt=False)

        assert result["encrypted"] is False
        assert result["encryption_key"] is None
        assert isinstance(result["data"], dict)
        assert "sections" in result["data"]

    def test_csv_format(self, client, auth_header):
        from app.services.backup import create_backup

        with client.application.app_context():
            result = create_backup(1, format="csv", encrypt=False)

        assert result["format"] == "csv"
        assert isinstance(result["data"], str)

    def test_selective_backup(self, client, auth_header):
        from app.services.backup import create_backup

        with client.application.app_context():
            result = create_backup(
                1, backup_type="selective", sections=["profile", "categories"]
            )

        assert result["backup_type"] == "selective"

    def test_passphrase_encryption(self, client, auth_header):
        from app.services.backup import create_backup

        with client.application.app_context():
            result = create_backup(1, passphrase="my-secret-pass")

        # No generated key returned when passphrase is used
        assert result["encryption_key"] is None
        assert result["encrypted"] is True

    def test_backup_record_created(self, client, auth_header):
        from app.services.backup import create_backup
        from app.models import BackupRecord

        with client.application.app_context():
            result = create_backup(1)
            bid = result["backup_id"]
            rec = BackupRecord.query.get(bid)
            assert rec is not None
            assert rec.user_id == 1
            assert rec.status == "completed"


# ═══════════════════════════════════════════════════════════════════
# verify_backup tests
# ═══════════════════════════════════════════════════════════════════


class TestVerifyBackup:
    """Test verify_backup service function."""

    def test_verify_plain_backup_valid(self, client, auth_header):
        from app.services.backup import create_backup, verify_backup

        with client.application.app_context():
            backup = create_backup(1, encrypt=False)
            result = verify_backup(backup["data"], backup["file_hash"])

        assert result["verified"] is True
        assert result["encrypted"] is False

    def test_verify_plain_backup_invalid_hash(self, client, auth_header):
        from app.services.backup import create_backup, verify_backup

        with client.application.app_context():
            backup = create_backup(1, encrypt=False)
            result = verify_backup(backup["data"], "badhash")

        assert result["verified"] is False

    def test_verify_encrypted_backup(self, client, auth_header):
        from app.services.backup import create_backup, verify_backup

        with client.application.app_context():
            backup = create_backup(1, encrypt=True)
            result = verify_backup(backup["data"], backup["file_hash"])

        assert result["verified"] is True
        assert result["encrypted"] is True

    def test_verify_string_backup(self, client, auth_header):
        from app.services.backup import verify_backup

        raw = "sample csv data"
        h = hashlib.sha256(raw.encode()).hexdigest()
        with client.application.app_context():
            result = verify_backup(raw, h)
        assert result["verified"] is True


# ═══════════════════════════════════════════════════════════════════
# restore_preview tests
# ═══════════════════════════════════════════════════════════════════


class TestRestorePreview:
    """Test restore_preview service function."""

    def test_preview_unencrypted(self, client, auth_header):
        from app.services.backup import create_backup, restore_preview

        with client.application.app_context():
            backup = create_backup(1, encrypt=False)
            result = restore_preview(1, backup["data"])

        assert "sections" in result
        assert "exported_at" in result

    def test_preview_encrypted_with_key(self, client, auth_header):
        from app.services.backup import create_backup, restore_preview

        with client.application.app_context():
            backup = create_backup(1, encrypt=True)
            result = restore_preview(1, backup["data"], encryption_key=backup["encryption_key"])

        assert "sections" in result

    def test_preview_encrypted_with_passphrase(self, client, auth_header):
        from app.services.backup import create_backup, restore_preview

        with client.application.app_context():
            backup = create_backup(1, passphrase="my-pass")
            result = restore_preview(1, backup["data"], passphrase="my-pass")

        assert "sections" in result

    def test_preview_encrypted_missing_key(self, client, auth_header):
        from app.services.backup import create_backup, restore_preview

        with client.application.app_context():
            backup = create_backup(1, encrypt=True)
            result = restore_preview(1, backup["data"])

        assert "error" in result

    def test_preview_wrong_key_fails(self, client, auth_header):
        from app.services.backup import create_backup, restore_preview

        with client.application.app_context():
            backup = create_backup(1, encrypt=True)
            wrong_key = base64.b64encode(b"x" * 32).decode()
            result = restore_preview(1, backup["data"], encryption_key=wrong_key)

        assert "error" in result

    def test_preview_invalid_format(self, client, auth_header):
        from app.services.backup import restore_preview

        with client.application.app_context():
            result = restore_preview(1, "not a dict")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════
# History & delete tests
# ═══════════════════════════════════════════════════════════════════


class TestBackupHistory:
    """Test get_backup_history and delete_backup_record."""

    def test_empty_history(self, client, auth_header):
        from app.services.backup import get_backup_history

        with client.application.app_context():
            records = get_backup_history(1)
        assert records == []

    def test_history_returns_records(self, client, auth_header):
        from app.services.backup import create_backup, get_backup_history

        with client.application.app_context():
            create_backup(1)
            create_backup(1)
            records = get_backup_history(1)

        assert len(records) == 2
        assert records[0]["status"] == "completed"

    def test_history_limit(self, client, auth_header):
        from app.services.backup import create_backup, get_backup_history

        with client.application.app_context():
            for _ in range(5):
                create_backup(1)
            records = get_backup_history(1, limit=3)

        assert len(records) == 3

    def test_delete_record(self, client, auth_header):
        from app.services.backup import create_backup, delete_backup_record, get_backup_history

        with client.application.app_context():
            result = create_backup(1)
            bid = result["backup_id"]
            assert delete_backup_record(1, bid) is True
            assert get_backup_history(1) == []

    def test_delete_nonexistent(self, client, auth_header):
        from app.services.backup import delete_backup_record

        with client.application.app_context():
            assert delete_backup_record(1, 9999) is False

    def test_delete_wrong_user(self, client, auth_header):
        from app.services.backup import create_backup, delete_backup_record

        with client.application.app_context():
            result = create_backup(1)
            bid = result["backup_id"]
            # User 999 cannot delete user 1's backup
            assert delete_backup_record(999, bid) is False


# ═══════════════════════════════════════════════════════════════════
# Route integration tests
# ═══════════════════════════════════════════════════════════════════


class TestBackupRoutes:
    """Integration tests for /backup/* endpoints."""

    # ── POST /backup/create ──
    def test_create_backup_default(self, client, auth_header):
        r = client.post("/backup/create", json={}, headers=auth_header)
        assert r.status_code == 201
        body = r.get_json()
        assert body["backup_type"] == "full"
        assert body["format"] == "json"
        assert body["encrypted"] is True
        assert "encryption_key" in body

    def test_create_backup_unencrypted_csv(self, client, auth_header):
        r = client.post("/backup/create", json={
            "format": "csv",
            "encrypt": False,
        }, headers=auth_header)
        assert r.status_code == 201
        body = r.get_json()
        assert body["format"] == "csv"
        assert body["encrypted"] is False

    def test_create_backup_selective(self, client, auth_header):
        r = client.post("/backup/create", json={
            "backup_type": "selective",
            "sections": ["profile"],
        }, headers=auth_header)
        assert r.status_code == 201

    def test_create_backup_passphrase(self, client, auth_header):
        r = client.post("/backup/create", json={
            "passphrase": "strong-pass",
        }, headers=auth_header)
        assert r.status_code == 201
        body = r.get_json()
        assert body["encrypted"] is True
        assert body["encryption_key"] is None  # no raw key returned

    def test_create_backup_unauthorized(self, client):
        r = client.post("/backup/create", json={})
        assert r.status_code == 401

    # ── POST /backup/verify ──
    def test_verify_success(self, client, auth_header):
        # Create an encrypted backup — encrypted backups always verify structure
        cr = client.post("/backup/create", json={"encrypt": True}, headers=auth_header)
        backup = cr.get_json()
        r = client.post("/backup/verify", json={
            "data": backup["data"],
            "file_hash": backup["file_hash"],
        }, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["verified"] is True

    def test_verify_missing_fields(self, client, auth_header):
        r = client.post("/backup/verify", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_verify_bad_hash(self, client, auth_header):
        cr = client.post("/backup/create", json={"encrypt": False}, headers=auth_header)
        backup = cr.get_json()
        r = client.post("/backup/verify", json={
            "data": backup["data"],
            "file_hash": "wrong",
        }, headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["verified"] is False

    # ── POST /backup/restore/preview ──
    def test_restore_preview_unencrypted(self, client, auth_header):
        cr = client.post("/backup/create", json={"encrypt": False}, headers=auth_header)
        backup = cr.get_json()
        r = client.post("/backup/restore/preview", json={
            "data": backup["data"],
        }, headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert "sections" in body

    def test_restore_preview_encrypted_with_key(self, client, auth_header):
        cr = client.post("/backup/create", json={}, headers=auth_header)
        backup = cr.get_json()
        r = client.post("/backup/restore/preview", json={
            "data": backup["data"],
            "encryption_key": backup["encryption_key"],
        }, headers=auth_header)
        assert r.status_code == 200

    def test_restore_preview_missing_data(self, client, auth_header):
        r = client.post("/backup/restore/preview", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_restore_preview_no_key_for_encrypted(self, client, auth_header):
        cr = client.post("/backup/create", json={}, headers=auth_header)
        backup = cr.get_json()
        r = client.post("/backup/restore/preview", json={
            "data": backup["data"],
        }, headers=auth_header)
        assert r.status_code == 400

    # ── GET /backup/history ──
    def test_history_empty(self, client, auth_header):
        r = client.get("/backup/history", headers=auth_header)
        assert r.status_code == 200
        body = r.get_json()
        assert body["backups"] == []
        assert body["count"] == 0

    def test_history_after_create(self, client, auth_header):
        client.post("/backup/create", json={}, headers=auth_header)
        client.post("/backup/create", json={"format": "csv"}, headers=auth_header)
        r = client.get("/backup/history", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 2

    def test_history_limit_param(self, client, auth_header):
        for _ in range(5):
            client.post("/backup/create", json={}, headers=auth_header)
        r = client.get("/backup/history?limit=2", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["count"] == 2

    # ── DELETE /backup/<id> ──
    def test_delete_backup(self, client, auth_header):
        cr = client.post("/backup/create", json={}, headers=auth_header)
        bid = cr.get_json()["backup_id"]
        r = client.delete(f"/backup/{bid}", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["message"] == "Backup deleted"

    def test_delete_nonexistent(self, client, auth_header):
        r = client.delete("/backup/9999", headers=auth_header)
        assert r.status_code == 404

    def test_delete_unauthorized(self, client):
        r = client.delete("/backup/1")
        assert r.status_code == 401
