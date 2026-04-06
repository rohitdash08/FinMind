import secrets
from app.services.client_encryption import encrypt_payload, decrypt_payload, encrypt_field, decrypt_field, sign_data

def test_roundtrip():
    key = secrets.token_bytes(32)
    data = {"amount": 150.0, "note": "Groceries"}
    assert decrypt_payload(encrypt_payload(data, key), key) == data

def test_wrong_key_fails():
    import pytest
    key1, key2 = secrets.token_bytes(32), secrets.token_bytes(32)
    enc = encrypt_payload({"x": 1}, key1)
    with pytest.raises(Exception): decrypt_payload(enc, key2)

def test_field_encryption():
    key = secrets.token_bytes(32)
    assert decrypt_field(encrypt_field("John Doe", key), key) == "John Doe"

def test_hmac():
    sig = sign_data({"a": 1}, secrets.token_bytes(32))
    assert len(sig) == 64
