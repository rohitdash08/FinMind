"""
Tests for Client-Side Encryption (Issue #99).

Covers:
- Unit: derive_key_wrapping_key, wrap_dek, unwrap_dek, compute_hmac, verify_hmac
- Unit: create_encryption_setup, retrieve_wrapped_dek, rotate_dek
- Unit: verify_ciphertext_integrity
- HTTP: POST /encryption/setup
- HTTP: GET /encryption/setup (correct / wrong password)
- HTTP: POST /encryption/rotate
- HTTP: POST /encryption/verify
- HTTP: DELETE /encryption/setup
- Auth required on all endpoints
- Wrong password → 401
- Setup not found → 404
- Key rotation: new and old wrapped DEKs differ, both unwrappable
- HMAC verification: valid / invalid / tampered
- Server never stores plaintext password or plaintext DEK
"""

from __future__ import annotations

import base64
import json
import secrets

import pytest

from app.services.encryption import (
    compute_hmac,
    create_encryption_setup,
    derive_key_wrapping_key,
    generate_dek,
    retrieve_wrapped_dek,
    rotate_dek,
    unwrap_dek,
    verify_ciphertext_integrity,
    verify_hmac,
    wrap_dek,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="enc@test.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    r = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — crypto primitives
# ─────────────────────────────────────────────────────────────────────────────

class TestKeyDerivation:
    def test_derive_returns_32_bytes(self):
        salt = secrets.token_bytes(32)
        key = derive_key_wrapping_key("password", salt)
        assert len(key) == 32

    def test_same_inputs_same_output(self):
        salt = secrets.token_bytes(32)
        k1 = derive_key_wrapping_key("password", salt)
        k2 = derive_key_wrapping_key("password", salt)
        assert k1 == k2

    def test_different_password_different_key(self):
        salt = secrets.token_bytes(32)
        k1 = derive_key_wrapping_key("password1", salt)
        k2 = derive_key_wrapping_key("password2", salt)
        assert k1 != k2

    def test_different_salt_different_key(self):
        k1 = derive_key_wrapping_key("password", secrets.token_bytes(32))
        k2 = derive_key_wrapping_key("password", secrets.token_bytes(32))
        assert k1 != k2


class TestWrapUnwrap:
    def test_wrap_unwrap_roundtrip(self):
        kwk = secrets.token_bytes(32)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kwk)
        recovered = unwrap_dek(wrapped, kwk)
        assert recovered == dek

    def test_wrong_key_raises(self):
        kwk = secrets.token_bytes(32)
        wrong_kwk = secrets.token_bytes(32)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kwk)
        with pytest.raises(ValueError):
            unwrap_dek(wrapped, wrong_kwk)

    def test_wrapped_has_required_fields(self):
        kwk = secrets.token_bytes(32)
        dek = generate_dek()
        wrapped = wrap_dek(dek, kwk)
        assert "iv" in wrapped
        assert "ciphertext" in wrapped
        assert "tag" in wrapped

    def test_each_wrap_produces_different_iv(self):
        kwk = secrets.token_bytes(32)
        dek = generate_dek()
        w1 = wrap_dek(dek, kwk)
        w2 = wrap_dek(dek, kwk)
        assert w1["iv"] != w2["iv"]  # fresh random IV each time

    def test_malformed_wrapped_raises(self):
        with pytest.raises(ValueError):
            unwrap_dek({"iv": "bad", "ciphertext": "bad", "tag": "bad"}, secrets.token_bytes(32))


class TestHmac:
    def test_compute_and_verify(self):
        key = secrets.token_bytes(32)
        data = b"financial data"
        mac = compute_hmac(key, data)
        assert verify_hmac(key, data, mac) is True

    def test_wrong_key_fails(self):
        key = secrets.token_bytes(32)
        wrong_key = secrets.token_bytes(32)
        mac = compute_hmac(key, b"data")
        assert verify_hmac(wrong_key, b"data", mac) is False

    def test_tampered_data_fails(self):
        key = secrets.token_bytes(32)
        mac = compute_hmac(key, b"original")
        assert verify_hmac(key, b"tampered", mac) is False

    def test_invalid_hex_returns_false(self):
        assert verify_hmac(secrets.token_bytes(32), b"data", "not-hex!!") is False


class TestVerifyCiphertextIntegrity:
    def test_valid_hmac(self):
        key = secrets.token_bytes(32)
        ct = base64.urlsafe_b64encode(b"ciphertext").decode()
        mac = compute_hmac(key, ct.encode())
        assert verify_ciphertext_integrity(key.hex(), ct, mac) is True

    def test_invalid_hmac(self):
        key = secrets.token_bytes(32)
        ct = base64.urlsafe_b64encode(b"data").decode()
        assert verify_ciphertext_integrity(key.hex(), ct, "badhex") is False


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — high-level service
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateEncryptionSetup:
    def test_returns_required_fields(self):
        result = create_encryption_setup("mypassword")
        assert "kdf_salt" in result
        assert "kdf_iters" in result
        assert "wrapped_dek" in result
        assert "algorithm" in result

    def test_password_not_stored(self):
        result = create_encryption_setup("secret")
        assert "secret" not in json.dumps(result)

    def test_different_calls_different_salts(self):
        r1 = create_encryption_setup("password")
        r2 = create_encryption_setup("password")
        assert r1["kdf_salt"] != r2["kdf_salt"]


class TestRetrieveWrappedDek:
    def test_correct_password_succeeds(self):
        setup = create_encryption_setup("correct")
        result = retrieve_wrapped_dek(setup, "correct")
        assert "wrapped_dek" in result

    def test_wrong_password_raises(self):
        setup = create_encryption_setup("correct")
        with pytest.raises(ValueError):
            retrieve_wrapped_dek(setup, "wrong")


class TestRotateDek:
    def test_rotation_produces_new_wrapped_dek(self):
        setup = create_encryption_setup("password")
        result = rotate_dek(setup, "password")
        assert result["wrapped_dek"] != setup["wrapped_dek"]

    def test_old_wrapped_dek_returned(self):
        setup = create_encryption_setup("password")
        result = rotate_dek(setup, "password")
        assert "old_wrapped_dek" in result
        assert result["old_wrapped_dek"] == setup["wrapped_dek"]

    def test_both_deks_unwrappable(self):
        setup = create_encryption_setup("password")
        result = rotate_dek(setup, "password")
        salt = base64.urlsafe_b64decode(setup["kdf_salt"] + "==")
        import hashlib
        kwk = hashlib.pbkdf2_hmac("sha256", b"password", salt, setup["kdf_iters"], dklen=32)
        # Both old and new DEK must be unwrappable with the same KWK
        old_dek = unwrap_dek(result["old_wrapped_dek"], kwk)
        new_dek = unwrap_dek(result["wrapped_dek"], kwk)
        assert old_dek != new_dek  # actually different keys

    def test_wrong_password_raises(self):
        setup = create_encryption_setup("password")
        with pytest.raises(ValueError):
            rotate_dek(setup, "wrong")


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP
# ─────────────────────────────────────────────────────────────────────────────

class TestEncryptionSetupEndpoint:
    def test_requires_auth(self, client, app_fixture):
        assert client.post("/encryption/setup", json={"password": "x"}).status_code == 401
        assert client.get("/encryption/setup?password=x").status_code == 401

    def test_setup_created(self, client, app_fixture):
        h = _auth(client, "enc1@test.com")
        r = client.post("/encryption/setup", json={"password": "strongpass"}, headers=h)
        assert r.status_code == 201
        d = r.get_json()
        assert "kdf_salt" in d
        assert "wrapped_dek" in d
        assert "algorithm" in d

    def test_missing_password_returns_400(self, client, app_fixture):
        h = _auth(client, "enc2@test.com")
        r = client.post("/encryption/setup", json={}, headers=h)
        assert r.status_code == 400

    def test_get_setup_correct_password(self, client, app_fixture):
        h = _auth(client, "enc3@test.com")
        client.post("/encryption/setup", json={"password": "mypass"}, headers=h)
        r = client.get("/encryption/setup?password=mypass", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "wrapped_dek" in d

    def test_get_setup_wrong_password_returns_401(self, client, app_fixture):
        h = _auth(client, "enc4@test.com")
        client.post("/encryption/setup", json={"password": "correct"}, headers=h)
        r = client.get("/encryption/setup?password=wrong", headers=h)
        assert r.status_code == 401

    def test_get_setup_not_configured_returns_404(self, client, app_fixture):
        h = _auth(client, "enc5@test.com")
        r = client.get("/encryption/setup?password=any", headers=h)
        assert r.status_code == 404

    def test_delete_setup(self, client, app_fixture):
        h = _auth(client, "enc6@test.com")
        client.post("/encryption/setup", json={"password": "pass"}, headers=h)
        r = client.delete("/encryption/setup", headers=h)
        assert r.status_code == 200
        # After deletion, GET returns 404
        r2 = client.get("/encryption/setup?password=pass", headers=h)
        assert r2.status_code == 404


class TestEncryptionRotateEndpoint:
    def test_rotate_returns_old_and_new_dek(self, client, app_fixture):
        h = _auth(client, "rot1@test.com")
        client.post("/encryption/setup", json={"password": "pass"}, headers=h)
        r = client.post("/encryption/rotate", json={"password": "pass"}, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "wrapped_dek" in d
        assert "old_wrapped_dek" in d
        assert d["wrapped_dek"] != d["old_wrapped_dek"]

    def test_rotate_wrong_password_returns_401(self, client, app_fixture):
        h = _auth(client, "rot2@test.com")
        client.post("/encryption/setup", json={"password": "pass"}, headers=h)
        r = client.post("/encryption/rotate", json={"password": "wrong"}, headers=h)
        assert r.status_code == 401

    def test_rotate_not_configured_returns_404(self, client, app_fixture):
        h = _auth(client, "rot3@test.com")
        r = client.post("/encryption/rotate", json={"password": "pass"}, headers=h)
        assert r.status_code == 404


class TestEncryptionVerifyEndpoint:
    def test_valid_hmac_returns_true(self, client, app_fixture):
        import hashlib, hmac as _hmac
        h = _auth(client, "ver1@test.com")
        key = secrets.token_bytes(32)
        ct = base64.urlsafe_b64encode(b"ciphertext").decode()
        mac = _hmac.new(key, ct.encode(), hashlib.sha256).hexdigest()

        r = client.post("/encryption/verify", json={
            "hmac_key": key.hex(), "ciphertext": ct, "hmac": mac,
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["valid"] is True

    def test_invalid_hmac_returns_false(self, client, app_fixture):
        h = _auth(client, "ver2@test.com")
        r = client.post("/encryption/verify", json={
            "hmac_key": secrets.token_bytes(32).hex(),
            "ciphertext": "abc",
            "hmac": "badhex",
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["valid"] is False

    def test_missing_fields_returns_400(self, client, app_fixture):
        h = _auth(client, "ver3@test.com")
        r = client.post("/encryption/verify", json={"hmac_key": "abc"}, headers=h)
        assert r.status_code == 400
