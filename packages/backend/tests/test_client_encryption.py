"""Tests for Client-Side Encryption service."""
import pytest
from app.services.client_encryption import (
    encrypt_field,
    decrypt_field,
    generate_user_key_material,
    test_encryption_roundtrip,
    KEY_LENGTH,
    SALT_LENGTH,
    NONCE_LENGTH,
)


PASSWORD = "test-password-12345"


# ── Round-trip correctness ────────────────────────────────────────────

def test_encrypt_decrypt_short_string():
    plaintext = "Hello, World!"
    enc = encrypt_field(plaintext, PASSWORD)
    dec = decrypt_field(enc, PASSWORD)
    assert dec == plaintext


def test_encrypt_decrypt_long_string():
    plaintext = "A" * 1024  # 1KB
    enc = encrypt_field(plaintext, PASSWORD)
    dec = decrypt_field(enc, PASSWORD)
    assert dec == plaintext


def test_encrypt_decrypt_unicode():
    plaintext = "Montant: 1 234,56 € — Paiement réussi"
    enc = encrypt_field(plaintext, PASSWORD)
    dec = decrypt_field(enc, PASSWORD)
    assert dec == plaintext


def test_encrypt_empty_string():
    enc = encrypt_field("", PASSWORD)
    dec = decrypt_field(enc, PASSWORD)
    assert dec == ""


# ── Non-determinism (different every call) ────────────────────────────

def test_encrypt_different_each_call():
    enc1 = encrypt_field("same", PASSWORD)
    enc2 = encrypt_field("same", PASSWORD)
    assert enc1 != enc2  # Different random salt+nonce each time


# ── Authentication tag ────────────────────────────────────────────────

def test_wrong_password_raises():
    enc = encrypt_field("secret", PASSWORD)
    with pytest.raises(ValueError, match="Authentication failed"):
        decrypt_field(enc, "wrong-password")


def test_tampered_ciphertext_raises():
    import base64
    enc = encrypt_field("secret", PASSWORD)
    blob = bytearray(base64.b64decode(enc))
    # Flip last byte
    blob[-1] ^= 0xFF
    tampered = base64.b64encode(bytes(blob)).decode("ascii")
    with pytest.raises(ValueError):
        decrypt_field(tampered, PASSWORD)


def test_too_short_blob_raises():
    with pytest.raises(ValueError, match="too short"):
        decrypt_field("AAAA", PASSWORD)


# ── Key material ──────────────────────────────────────────────────────

def test_keygen_fields():
    material = generate_user_key_material(1)
    assert "key_id" in material
    assert "salt" in material
    assert "algorithm" in material
    assert "iterations" in material
    assert material["iterations"] == 100_000


def test_keygen_different_each_call():
    m1 = generate_user_key_material(1)
    m2 = generate_user_key_material(1)
    assert m1["key_id"] != m2["key_id"]  # Different salt = different key_id


# ── Self-test ─────────────────────────────────────────────────────────

def test_encryption_roundtrip_success():
    result = test_encryption_roundtrip("test data", PASSWORD)
    assert result.success is True
    assert result.original_length == 9
    assert result.encrypted_length > 9
    assert result.error is None