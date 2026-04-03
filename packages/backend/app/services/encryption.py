from __future__ import annotations

"""
Client-Side Encryption Layer (Issue #99)

Provides helpers for envelope encryption:
  1. A per-user Data Encryption Key (DEK) is generated and stored encrypted
     under the user's Key Encryption Key (KEK) derived from their password.
  2. Sensitive fields (notes, category names) are encrypted with AES-256-GCM
     before being persisted.
  3. Decryption happens on the server only when the client presents the correct
     KEK material — the server never stores plaintext DEKs or master keys.

Key derivation: PBKDF2-HMAC-SHA256 (100 000 iterations).
Encryption: AES-256-GCM with a random 12-byte nonce per ciphertext.
Storage format (base64): nonce || tag || ciphertext
"""

import base64
import hashlib
import hmac
import os
import struct
from typing import Optional

# Optional pycryptodome support, fallback to stdlib hmac/hashlib for key ops
try:
    from Crypto.Cipher import AES as _AES  # type: ignore
    from Crypto.Random import get_random_bytes  # type: ignore
    _CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    _CRYPTO_AVAILABLE = False

from app.models import db, User


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 100_000
_KEY_LEN = 32  # AES-256
_NONCE_LEN = 12
_TAG_LEN = 16
_SALT_LEN = 16


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def derive_kek(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit Key Encryption Key from a user password."""
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
        dklen=_KEY_LEN,
    )


def generate_dek() -> bytes:
    """Generate a random 256-bit Data Encryption Key."""
    return os.urandom(_KEY_LEN)


# ---------------------------------------------------------------------------
# AES-256-GCM helpers
# ---------------------------------------------------------------------------

def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> bytes:
    """Return nonce + tag + ciphertext (all binary)."""
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "pycryptodome required for encryption (pip install pycryptodome)"
        )
    nonce = get_random_bytes(_NONCE_LEN)
    cipher = _AES.new(key, _AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext)
    return nonce + tag + ciphertext


def _aes_gcm_decrypt(key: bytes, blob: bytes) -> bytes:
    """Decrypt nonce + tag + ciphertext blob."""
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "pycryptodome required for decryption (pip install pycryptodome)"
        )
    nonce = blob[:_NONCE_LEN]
    tag = blob[_NONCE_LEN: _NONCE_LEN + _TAG_LEN]
    ciphertext = blob[_NONCE_LEN + _TAG_LEN:]
    cipher = _AES.new(key, _AES.MODE_GCM, nonce=nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)


# ---------------------------------------------------------------------------
# High-level API
# ---------------------------------------------------------------------------

def setup_user_encryption(uid: int, password: str) -> dict:
    """
    Generate a fresh DEK for the user, encrypt it under a KEK derived from
    their password, and store the encrypted DEK + salt in the User record.

    Returns: {salt: hex, encrypted_dek: base64, algorithm: str}
    """
    salt = os.urandom(_SALT_LEN)
    kek = derive_kek(password, salt)
    dek = generate_dek()
    encrypted_dek = _aes_gcm_encrypt(kek, dek)

    user = db.session.query(User).filter_by(id=uid).first()
    if user is None:
        raise ValueError(f"User {uid} not found")

    # Store as hex/b64 in dedicated columns (add via migration if needed)
    if hasattr(user, "enc_salt"):
        user.enc_salt = salt.hex()
    if hasattr(user, "enc_dek"):
        user.enc_dek = base64.b64encode(encrypted_dek).decode()
    db.session.commit()

    return {
        "salt": salt.hex(),
        "encrypted_dek": base64.b64encode(encrypted_dek).decode(),
        "algorithm": "AES-256-GCM",
        "kdf": f"PBKDF2-SHA256/{_PBKDF2_ITERATIONS}",
    }


def _get_user_dek(uid: int, password: str) -> bytes:
    """Retrieve and decrypt the user DEK using their password."""
    user = db.session.query(User).filter_by(id=uid).first()
    if user is None:
        raise ValueError(f"User {uid} not found")
    salt_hex = getattr(user, "enc_salt", None)
    enc_dek_b64 = getattr(user, "enc_dek", None)
    if not salt_hex or not enc_dek_b64:
        raise ValueError("Encryption not set up for this user")
    salt = bytes.fromhex(salt_hex)
    kek = derive_kek(password, salt)
    encrypted_dek = base64.b64decode(enc_dek_b64)
    return _aes_gcm_decrypt(kek, encrypted_dek)


def encrypt_field(uid: int, password: str, plaintext: str) -> str:
    """Encrypt a single field string. Returns base64-encoded ciphertext."""
    dek = _get_user_dek(uid, password)
    blob = _aes_gcm_encrypt(dek, plaintext.encode("utf-8"))
    return base64.b64encode(blob).decode()


def decrypt_field(uid: int, password: str, ciphertext_b64: str) -> str:
    """Decrypt a base64-encoded ciphertext field. Returns plaintext string."""
    dek = _get_user_dek(uid, password)
    blob = base64.b64decode(ciphertext_b64)
    return _aes_gcm_decrypt(dek, blob).decode("utf-8")


def re_encrypt_dek(uid: int, old_password: str, new_password: str) -> dict:
    """
    Re-wrap the DEK under a new KEK (used on password change).
    The DEK itself stays the same — all encrypted data remains valid.
    """
    dek = _get_user_dek(uid, old_password)
    new_salt = os.urandom(_SALT_LEN)
    new_kek = derive_kek(new_password, new_salt)
    new_encrypted_dek = _aes_gcm_encrypt(new_kek, dek)

    user = db.session.query(User).filter_by(id=uid).first()
    if hasattr(user, "enc_salt"):
        user.enc_salt = new_salt.hex()
    if hasattr(user, "enc_dek"):
        user.enc_dek = base64.b64encode(new_encrypted_dek).decode()
    db.session.commit()

    return {
        "salt": new_salt.hex(),
        "encrypted_dek": base64.b64encode(new_encrypted_dek).decode(),
    }


def check_encryption_status(uid: int) -> dict:
    """Return whether encryption is configured for the user."""
    user = db.session.query(User).filter_by(id=uid).first()
    if user is None:
        return {"enabled": False, "reason": "user not found"}
    has_salt = bool(getattr(user, "enc_salt", None))
    has_dek = bool(getattr(user, "enc_dek", None))
    return {
        "enabled": has_salt and has_dek,
        "algorithm": "AES-256-GCM" if (has_salt and has_dek) else None,
        "kdf": f"PBKDF2-SHA256/{_PBKDF2_ITERATIONS}" if (has_salt and has_dek) else None,
        "crypto_available": _CRYPTO_AVAILABLE,
    }
