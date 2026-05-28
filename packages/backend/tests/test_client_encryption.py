"""Tests for client-side encryption."""

import pytest


class TestEncryptionMetadata:
    def test_mark_encrypted(self):
        from app.services.client_encryption import EncryptionMetadata
        meta = EncryptionMetadata()
        meta.mark_encrypted("amount")
        assert meta.is_encrypted("amount")
        assert not meta.is_encrypted("merchant")

    def test_serialization(self):
        from app.services.client_encryption import EncryptionMetadata
        meta = EncryptionMetadata()
        meta.mark_encrypted("amount")
        meta.mark_encrypted("merchant")
        d = meta.to_dict()
        meta2 = EncryptionMetadata.from_dict(d)
        assert meta2.is_encrypted("amount")
        assert meta2.is_encrypted("merchant")


class TestKeyManager:
    def test_create_key(self):
        from app.services.client_encryption import KeyManager
        km = KeyManager("user1")
        key = km.create_key_version()
        assert key["version"] == 1
        assert key["status"] == "active"

    def test_rotate_key(self):
        from app.services.client_encryption import KeyManager
        km = KeyManager("user1")
        km.create_key_version()
        new_key = km.rotate_key()
        assert new_key["version"] == 2
        assert new_key["status"] == "active"

    def test_key_history(self):
        from app.services.client_encryption import KeyManager
        km = KeyManager("user1")
        km.create_key_version()
        km.create_key_version()
        history = km.get_key_history()
        assert len(history) == 2


class TestFieldEncryptor:
    def test_detect_encrypted(self):
        from app.services.client_encryption import FieldEncryptor
        assert FieldEncryptor.is_encrypted_value("enc:v1:aaaa:bbbb:cccc")
        assert not FieldEncryptor.is_encrypted_value("plain text")

    def test_validate_good_format(self):
        import base64
        from app.services.client_encryption import FieldEncryptor
        iv = base64.b64encode(b"0" * 12).decode()
        ct = base64.b64encode(b"ciphertext").decode()
        tag = base64.b64encode(b"tag1234567890123456").decode()
        value = f"enc:v1:{iv}:{ct}:{tag}"
        result = FieldEncryptor.validate_encrypted_field(value, "amount")
        assert result["valid"]

    def test_validate_record(self):
        from app.services.client_encryption import FieldEncryptor
        record = {"amount": 100, "merchant": "enc:v1:a:b:c"}
        result = FieldEncryptor.validate_encrypted_record(record, ["amount", "merchant"])
        assert not result["valid"]  # amount is numeric
