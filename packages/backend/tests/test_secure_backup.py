"""Tests for Secure Backup & Encrypted Export (issue #126)."""
import pytest
import json
import hashlib
from unittest.mock import MagicMock
from datetime import date

from app.services.secure_backup import (
    create_encrypted_export,
    encrypt_data,
    decrypt_data,
    ExportResult,
    EncryptedExport,
)


def _make_tx(tx_id, amount=100.0, tx_date=date(2026, 1, 15), category="Food"):
    tx = MagicMock()
    tx.id = tx_id
    tx.amount = amount
    tx.date = tx_date
    tx.type = "expense"
    tx.category = category
    tx.description = "Test transaction"
    return tx


def _mock_query(rows):
    q = MagicMock()
    q.filter.return_value = q
    q.in_.return_value = q
    q.all.return_value = rows
    return q


def test_encrypt_decrypt_roundtrip():
    original = "hello world financial data"
    encrypted, checksum = encrypt_data(original, "my-password")
    decrypted = decrypt_data(encrypted, "my-password")
    assert decrypted == original


def test_checksum_is_sha256():
    original = "test data"
    _, checksum = encrypt_data(original, "password")
    expected = hashlib.sha256(original.encode()).hexdigest()
    assert checksum == expected


def test_wrong_password_produces_garbage():
    original = "financial data 12345"
    encrypted, _ = encrypt_data(original, "correct-password")
    decrypted = decrypt_data(encrypted, "wrong-password")
    assert decrypted != original


def test_empty_transactions(mocker):
    mocker.patch("app.services.secure_backup.db.session.query",
                 return_value=_mock_query([]))
    result = create_encrypted_export(user_id=1, password="test123")
    assert result.export.record_count == 0
    assert result.export.encrypted_data  # still has encrypted empty payload


def test_required_fields(mocker):
    mocker.patch("app.services.secure_backup.db.session.query",
                 return_value=_mock_query([]))
    result = create_encrypted_export(user_id=1, password="test123")
    assert hasattr(result.export, "export_id")
    assert hasattr(result.export, "encrypted_data")
    assert hasattr(result.export, "checksum")
    assert hasattr(result.export, "record_count")
    assert hasattr(result.export, "created_at")


def test_encrypted_data_decryptable(mocker):
    txs = [_make_tx(1, 50.0)]
    mocker.patch("app.services.secure_backup.db.session.query",
                 return_value=_mock_query(txs))
    result = create_encrypted_export(user_id=1, password="mypassword")
    decrypted = decrypt_data(result.export.encrypted_data, "mypassword")
    payload = json.loads(decrypted)
    assert payload["record_count"] == 1
    assert len(payload["transactions"]) == 1


def test_record_count_matches(mocker):
    txs = [_make_tx(i) for i in range(5)]
    mocker.patch("app.services.secure_backup.db.session.query",
                 return_value=_mock_query(txs))
    result = create_encrypted_export(user_id=1, password="test")
    assert result.export.record_count == 5


def test_different_passwords_different_output():
    encrypted1, _ = encrypt_data("same data", "password1")
    encrypted2, _ = encrypt_data("same data", "password2")
    assert encrypted1 != encrypted2


def test_export_route_requires_auth(client):
    resp = client.post("/insights/export-encrypted", json={"password": "test"})
    assert resp.status_code == 401


def test_decrypt_route_requires_auth(client):
    resp = client.post("/insights/decrypt-export", json={"encrypted_data": "test", "password": "test"})
    assert resp.status_code == 401