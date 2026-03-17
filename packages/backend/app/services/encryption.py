"""
Client-Side Encryption for Financial Data (Issue #99).

Architecture
------------
Encryption is performed **on the client** using AES-256-GCM before data
reaches the server.  The server stores only ciphertext and never has access
to the plaintext or the user's encryption key.

Server-side responsibilities (this module):
1. Derive a per-user, per-field key-wrapping key from the user's password
   using PBKDF2-HMAC-SHA256 — the client can reproduce the same key from
   the same password and salt.
2. Wrap (encrypt) an AES-256 data-encryption key (DEK) using AES-256-GCM
   so the wrapped DEK can be stored server-side without exposing the DEK.
3. Unwrap the DEK so the client can retrieve it after authentication.
4. Rotate the DEK: re-wrap the existing DEK under a new key-wrapping key.
5. Validate integrity: verify an HMAC-SHA256 over ciphertext submitted by
   the client to detect tampering before storage.

Cryptographic primitives used
------------------------------
* AES-256-GCM  — authenticated encryption (data confidentiality + integrity)
* PBKDF2-HMAC-SHA256  — key derivation from password
* HMAC-SHA256  — integrity check on stored ciphertext

All operations use only Python's standard-library `hashlib`, `hmac`, and
`secrets` modules plus the `cryptography` package (already a common Flask dep).

Key rotation safety
-------------------
DEK rotation generates a new DEK and re-wraps it under the current KWK.
Old ciphertext encrypted under the previous DEK is NOT automatically
re-encrypted — the client must re-encrypt its local data and push it.
The rotation endpoint returns the new wrapped DEK so the client can decrypt
existing data with the old DEK and re-encrypt with the new one.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import logging
from typing import Any

logger = logging.getLogger("finmind.encryption")

# ── Constants ─────────────────────────────────────────────────────────────────

_KDF_ITERATIONS   = 260_000   # NIST SP 800-132 recommendation (2023)
_KEY_LEN          = 32        # AES-256
_SALT_LEN         = 32        # 256-bit KDF salt
_IV_LEN           = 12        # GCM standard nonce
_TAG_LEN          = 16        # GCM authentication tag
_HMAC_LEN         = 32        # HMAC-SHA256 output

# ── Low-level AES-GCM helpers (requires `cryptography`) ───────────────────────

def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> tuple[bytes, bytes, bytes]:
    """Return (iv, ciphertext, tag)."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = secrets.token_bytes(_IV_LEN)
    aesgcm = AESGCM(key)
    ct_with_tag = aesgcm.encrypt(iv, plaintext, None)
    # cryptography appends the 16-byte tag to ciphertext
    ciphertext = ct_with_tag[:-_TAG_LEN]
    tag = ct_with_tag[-_TAG_LEN:]
    return iv, ciphertext, tag


def _aes_gcm_decrypt(key: bytes, iv: bytes, ciphertext: bytes, tag: bytes) -> bytes:
    """Decrypt and authenticate; raises ValueError on auth failure."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(iv, ciphertext + tag, None)
    except Exception as exc:
        raise ValueError("decryption failed — invalid key or tampered ciphertext") from exc


# ── Key derivation ────────────────────────────────────────────────────────────

def derive_key_wrapping_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key-wrapping key (KWK) from a password using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _KDF_ITERATIONS,
        dklen=_KEY_LEN,
    )


# ── DEK lifecycle ─────────────────────────────────────────────────────────────

def generate_dek() -> bytes:
    """Generate a cryptographically random 256-bit data-encryption key."""
    return secrets.token_bytes(_KEY_LEN)


def wrap_dek(dek: bytes, kwk: bytes) -> dict[str, str]:
    """
    Encrypt (wrap) *dek* under *kwk* using AES-256-GCM.

    Returns a dict suitable for JSON storage:
        iv, ciphertext, tag — all base64url-encoded
    """
    iv, ct, tag = _aes_gcm_encrypt(kwk, dek)
    return {
        "iv":         base64.urlsafe_b64encode(iv).decode(),
        "ciphertext": base64.urlsafe_b64encode(ct).decode(),
        "tag":        base64.urlsafe_b64encode(tag).decode(),
    }


def unwrap_dek(wrapped: dict[str, str], kwk: bytes) -> bytes:
    """Decrypt the wrapped DEK using the key-wrapping key."""
    try:
        iv  = base64.urlsafe_b64decode(wrapped["iv"]  + "==")
        ct  = base64.urlsafe_b64decode(wrapped["ciphertext"] + "==")
        tag = base64.urlsafe_b64decode(wrapped["tag"] + "==")
    except (KeyError, ValueError) as exc:
        raise ValueError("malformed wrapped DEK") from exc
    return _aes_gcm_decrypt(kwk, iv, ct, tag)


# ── HMAC integrity check ──────────────────────────────────────────────────────

def compute_hmac(key: bytes, data: bytes) -> str:
    """Return HMAC-SHA256(key, data) as hex string."""
    return hmac.new(key, data, hashlib.sha256).hexdigest()


def verify_hmac(key: bytes, data: bytes, expected_hex: str) -> bool:
    """Constant-time HMAC verification. Returns True if valid."""
    actual = hmac.new(key, data, hashlib.sha256).digest()
    try:
        expected = bytes.fromhex(expected_hex)
    except ValueError:
        return False
    return hmac.compare_digest(actual, expected)


# ── High-level service functions ──────────────────────────────────────────────

def create_encryption_setup(password: str) -> dict[str, Any]:
    """
    Create the initial encryption setup for a user:
    1. Generate a random KDF salt
    2. Derive a KWK from password + salt
    3. Generate a fresh DEK
    4. Wrap the DEK under the KWK

    Returns everything the server needs to store (salt + wrapped DEK).
    The password and DEK are NOT stored.
    """
    salt = secrets.token_bytes(_SALT_LEN)
    kwk  = derive_key_wrapping_key(password, salt)
    dek  = generate_dek()
    wrapped = wrap_dek(dek, kwk)

    return {
        "kdf_salt":    base64.urlsafe_b64encode(salt).decode(),
        "kdf_iters":   _KDF_ITERATIONS,
        "wrapped_dek": wrapped,
        # version tag for future algorithm agility
        "algorithm":   "AES-256-GCM+PBKDF2-SHA256",
    }


def retrieve_wrapped_dek(
    stored_setup: dict[str, Any],
    password: str,
) -> dict[str, Any]:
    """
    Derive the KWK from the stored salt + the user-supplied password and
    verify that the wrapped DEK can be unwrapped (authentication check).

    Returns the wrapped DEK so the client can unwrap it locally.
    Raises ValueError on wrong password or tampered data.
    """
    try:
        salt = base64.urlsafe_b64decode(stored_setup["kdf_salt"] + "==")
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid stored setup") from exc

    iters = stored_setup.get("kdf_iters", _KDF_ITERATIONS)
    kwk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=_KEY_LEN)

    # Verify unwrappability (raises ValueError on wrong password)
    unwrap_dek(stored_setup["wrapped_dek"], kwk)

    # Return only what the client needs to unwrap locally
    return {
        "kdf_salt":    stored_setup["kdf_salt"],
        "kdf_iters":   iters,
        "wrapped_dek": stored_setup["wrapped_dek"],
        "algorithm":   stored_setup.get("algorithm", "AES-256-GCM+PBKDF2-SHA256"),
    }


def rotate_dek(
    stored_setup: dict[str, Any],
    password: str,
) -> dict[str, Any]:
    """
    Rotate the DEK:
    1. Derive KWK from current password + salt
    2. Unwrap old DEK (verifies password)
    3. Generate a new DEK
    4. Wrap the new DEK under the same KWK

    Returns updated setup fields to store.
    The client must re-encrypt its local data using the new DEK.
    The OLD wrapped DEK is returned so the client can decrypt existing data first.
    """
    try:
        salt = base64.urlsafe_b64decode(stored_setup["kdf_salt"] + "==")
    except (KeyError, ValueError) as exc:
        raise ValueError("invalid stored setup") from exc

    iters = stored_setup.get("kdf_iters", _KDF_ITERATIONS)
    kwk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters, dklen=_KEY_LEN)

    # Verify we can unwrap the old DEK (authentication)
    old_dek = unwrap_dek(stored_setup["wrapped_dek"], kwk)

    # Generate and wrap the new DEK
    new_dek = generate_dek()
    new_wrapped = wrap_dek(new_dek, kwk)

    logger.info("DEK rotated")

    return {
        "kdf_salt":        stored_setup["kdf_salt"],
        "kdf_iters":       iters,
        "wrapped_dek":     new_wrapped,
        "old_wrapped_dek": stored_setup["wrapped_dek"],  # client needs this for re-encryption
        "algorithm":       stored_setup.get("algorithm", "AES-256-GCM+PBKDF2-SHA256"),
    }


def verify_ciphertext_integrity(
    hmac_key_hex: str,
    ciphertext_b64: str,
    submitted_hmac: str,
) -> bool:
    """
    Verify the HMAC-SHA256 a client submits alongside encrypted data before
    persisting it.  Returns True if valid.

    hmac_key_hex    — hex-encoded HMAC key (derived by the client, stored server-side)
    ciphertext_b64  — base64url-encoded ciphertext blob
    submitted_hmac  — hex-encoded HMAC submitted by the client
    """
    try:
        key = bytes.fromhex(hmac_key_hex)
        data = ciphertext_b64.encode("utf-8")
        return verify_hmac(key, data, submitted_hmac)
    except ValueError:
        return False
