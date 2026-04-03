import json

import pytest


def _create_category(client, auth_header, name="General"):
    r = client.post("/categories", json={"name": name}, headers=auth_header)
    assert r.status_code in (201, 409)
    r = client.get("/categories", headers=auth_header)
    assert r.status_code == 200
    cats = [c for c in r.get_json() if c["name"] == name]
    return cats[0]["id"]


def _seed_expenses(client, auth_header, cat_id):
    """Insert two sample expenses and return their data."""
    expenses = [
        {
            "amount": 42.50,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Coffee beans",
            "date": "2026-03-01",
        },
        {
            "amount": 120.00,
            "currency": "USD",
            "category_id": cat_id,
            "description": "Electricity bill",
            "date": "2026-03-15",
        },
    ]
    for exp in expenses:
        r = client.post("/expenses", json=exp, headers=auth_header)
        assert r.status_code == 201
    return expenses


# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------


class TestPasswordValidation:
    def test_export_json_rejects_missing_password(self, client, auth_header):
        r = client.post("/backup/export", json={}, headers=auth_header)
        assert r.status_code == 400
        assert "backup_password" in r.get_json()["error"]

    def test_export_json_rejects_short_password(self, client, auth_header):
        r = client.post(
            "/backup/export",
            json={"backup_password": "short"},
            headers=auth_header,
        )
        assert r.status_code == 400
        assert "at least" in r.get_json()["error"]

    def test_export_csv_rejects_missing_password(self, client, auth_header):
        r = client.post("/backup/export/csv", json={}, headers=auth_header)
        assert r.status_code == 400

    def test_import_rejects_missing_password(self, client, auth_header):
        r = client.post("/backup/import", json={}, headers=auth_header)
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# JSON export + import round-trip
# ---------------------------------------------------------------------------


class TestJsonExportImport:
    def test_export_returns_encrypted_envelope(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)

        r = client.post(
            "/backup/export",
            json={"backup_password": "strong-password-123"},
            headers=auth_header,
        )
        assert r.status_code == 200
        body = r.get_json()
        envelope = body["backup"]
        assert envelope["version"] == 1
        assert envelope["cipher"] == "aes-256-gcm"
        assert envelope["kdf"] == "pbkdf2-sha256"
        assert "ciphertext" in envelope
        assert "salt" in envelope
        assert "nonce" in envelope

    def test_export_import_roundtrip(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)
        password = "roundtrip-test-pw!"

        # Export
        r = client.post(
            "/backup/export",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]

        # Delete existing expenses so import can re-create them
        r = client.get("/expenses", headers=auth_header)
        assert r.status_code == 200
        for exp in r.get_json():
            dr = client.delete(f"/expenses/{exp['id']}", headers=auth_header)
            assert dr.status_code == 200

        # Import
        r = client.post(
            "/backup/import",
            json={"backup_password": password, "backup": envelope},
            headers=auth_header,
        )
        assert r.status_code == 200
        result = r.get_json()
        assert result["imported_expenses"] == 2
        assert result["skipped_duplicates"] == 0

        # Verify expenses are restored
        r = client.get("/expenses", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2

    def test_import_skips_duplicates(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)
        password = "dup-test-password!"

        # Export
        r = client.post(
            "/backup/export",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]

        # Import without deleting — should detect duplicates
        r = client.post(
            "/backup/import",
            json={"backup_password": password, "backup": envelope},
            headers=auth_header,
        )
        assert r.status_code == 200
        result = r.get_json()
        assert result["imported_expenses"] == 0
        assert result["skipped_duplicates"] == 2

    def test_import_wrong_password_fails(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)

        r = client.post(
            "/backup/export",
            json={"backup_password": "correct-password-123"},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]

        r = client.post(
            "/backup/import",
            json={"backup_password": "wrong-password-456", "backup": envelope},
            headers=auth_header,
        )
        assert r.status_code == 400
        assert "wrong password" in r.get_json()["error"].lower()

    def test_import_rejects_missing_backup_payload(self, client, auth_header):
        r = client.post(
            "/backup/import",
            json={"backup_password": "valid-password-123"},
            headers=auth_header,
        )
        assert r.status_code == 400
        assert "backup payload" in r.get_json()["error"]


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


class TestCsvExport:
    def test_export_csv_returns_encrypted_envelope(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)

        r = client.post(
            "/backup/export/csv",
            json={"backup_password": "csv-password-123"},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]
        assert envelope["cipher"] == "aes-256-gcm"

    def test_csv_export_decrypts_to_valid_csv(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)
        password = "csv-roundtrip-pw!"

        r = client.post(
            "/backup/export/csv",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]

        # Manually decrypt and verify CSV structure
        from app.routes.backup import _decrypt

        plaintext = _decrypt(envelope, password)
        csv_text = plaintext.decode("utf-8")
        assert "id,amount,currency,expense_type,category_id,description,date" in csv_text
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3  # header + 2 expense rows


# ---------------------------------------------------------------------------
# Backup history
# ---------------------------------------------------------------------------


class TestBackupHistory:
    def test_history_starts_empty(self, client, auth_header):
        r = client.get("/backup/history", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json() == []

    def test_history_records_exports(self, client, auth_header):
        cat_id = _create_category(client, auth_header)
        _seed_expenses(client, auth_header, cat_id)
        password = "history-test-pw!"

        # Do a JSON export
        r = client.post(
            "/backup/export",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200

        # Do a CSV export
        r = client.post(
            "/backup/export/csv",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200

        # Check history
        r = client.get("/backup/history", headers=auth_header)
        assert r.status_code == 200
        history = r.get_json()
        assert len(history) == 2
        # Most recent first
        assert history[0]["format"] == "csv"
        assert history[1]["format"] == "json"
        assert history[0]["record_count"] == 2


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


class TestAuthRequired:
    def test_export_requires_auth(self, client):
        r = client.post("/backup/export", json={"backup_password": "test1234"})
        assert r.status_code == 401

    def test_export_csv_requires_auth(self, client):
        r = client.post("/backup/export/csv", json={"backup_password": "test1234"})
        assert r.status_code == 401

    def test_import_requires_auth(self, client):
        r = client.post("/backup/import", json={"backup_password": "test1234"})
        assert r.status_code == 401

    def test_history_requires_auth(self, client):
        r = client.get("/backup/history")
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Encryption unit tests
# ---------------------------------------------------------------------------


class TestCryptoHelpers:
    def test_encrypt_decrypt_roundtrip(self):
        from app.routes.backup import _decrypt, _encrypt

        password = "unit-test-password!"
        data = b"hello world"
        envelope = _encrypt(data, password)
        result = _decrypt(envelope, password)
        assert result == data

    def test_decrypt_wrong_password_raises(self):
        from app.routes.backup import _decrypt, _encrypt

        envelope = _encrypt(b"secret", "correct-password!")
        with pytest.raises(ValueError, match="wrong password"):
            _decrypt(envelope, "incorrect-pw!")

    def test_decrypt_malformed_envelope_raises(self):
        from app.routes.backup import _decrypt

        with pytest.raises(ValueError, match="malformed"):
            _decrypt({"bad": "data"}, "password1234")

    def test_different_encryptions_produce_different_output(self):
        from app.routes.backup import _encrypt

        password = "same-password-test!"
        data = b"identical payload"
        e1 = _encrypt(data, password)
        e2 = _encrypt(data, password)
        # Random salt+nonce means different ciphertexts each time
        assert e1["ciphertext"] != e2["ciphertext"]


# ---------------------------------------------------------------------------
# Category merge on import
# ---------------------------------------------------------------------------


class TestCategoryMerge:
    def test_import_merges_categories_by_name(self, client, auth_header):
        """When a backup contains a category that already exists, import
        should map expenses to the existing category rather than creating
        a duplicate."""
        cat_id = _create_category(client, auth_header, name="Food")
        password = "merge-test-password!"

        # Create an expense under "Food"
        client.post(
            "/expenses",
            json={
                "amount": 10.0,
                "description": "Pizza",
                "date": "2026-04-01",
                "category_id": cat_id,
            },
            headers=auth_header,
        )

        # Export
        r = client.post(
            "/backup/export",
            json={"backup_password": password},
            headers=auth_header,
        )
        assert r.status_code == 200
        envelope = r.get_json()["backup"]

        # Delete expense but keep category
        r = client.get("/expenses", headers=auth_header)
        for exp in r.get_json():
            client.delete(f"/expenses/{exp['id']}", headers=auth_header)

        # Import — "Food" category already exists, should not duplicate
        r = client.post(
            "/backup/import",
            json={"backup_password": password, "backup": envelope},
            headers=auth_header,
        )
        assert r.status_code == 200
        result = r.get_json()
        assert result["imported_categories"] == 0
        assert result["imported_expenses"] == 1

        # Verify only one "Food" category exists
        r = client.get("/categories", headers=auth_header)
        food_cats = [c for c in r.get_json() if c["name"] == "Food"]
        assert len(food_cats) == 1
