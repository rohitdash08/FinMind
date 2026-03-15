"""Secure backup & encrypted export service.

Provides AES-256-GCM encryption for financial data exports and supports
JSON and CSV formats.
"""

import csv
import io
import json
import os
import base64
import logging
from datetime import datetime, date, timezone
from decimal import Decimal
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("finmind.backup")

# 256-bit key derived from user-provided passphrase via PBKDF2
_PBKDF2_ITERATIONS = 600_000
_SALT_SIZE = 16  # 128-bit salt
_NONCE_SIZE = 12  # 96-bit nonce for AES-GCM
_KEY_SIZE = 32  # 256-bit key


class DecryptionError(Exception):
    """Raised when decryption fails (wrong key or corrupted data)."""


def derive_key(passphrase: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """Derive a 256-bit key from a passphrase using PBKDF2-HMAC-SHA256.

    Returns (key, salt).
    """
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes

    if salt is None:
        salt = os.urandom(_SALT_SIZE)

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_SIZE,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    return key, salt


def encrypt_data(plaintext: bytes, passphrase: str) -> bytes:
    """Encrypt data using AES-256-GCM.

    Output format: salt (16 bytes) || nonce (12 bytes) || ciphertext+tag
    """
    salt = os.urandom(_SALT_SIZE)
    key, _ = derive_key(passphrase, salt)
    nonce = os.urandom(_NONCE_SIZE)

    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)

    # Prepend salt and nonce
    return salt + nonce + ciphertext


def decrypt_data(encrypted: bytes, passphrase: str) -> bytes:
    """Decrypt AES-256-GCM encrypted data.

    Expects format: salt (16 bytes) || nonce (12 bytes) || ciphertext+tag
    """
    if len(encrypted) < _SALT_SIZE + _NONCE_SIZE + 16:
        raise DecryptionError("Data too short to be valid encrypted payload")

    salt = encrypted[:_SALT_SIZE]
    nonce = encrypted[_SALT_SIZE : _SALT_SIZE + _NONCE_SIZE]
    ciphertext = encrypted[_SALT_SIZE + _NONCE_SIZE :]

    key, _ = derive_key(passphrase, salt)

    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, associated_data=None)
    except Exception as exc:
        raise DecryptionError(f"Decryption failed: {exc}") from exc


def _serialize_value(val: Any) -> Any:
    """Convert non-JSON-serializable values."""
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    return val


def export_to_json(data: dict[str, list[dict]]) -> str:
    """Export structured data as formatted JSON.

    Args:
        data: Dict of model_name -> list of row dicts.

    Returns:
        JSON string with metadata header.
    """
    payload = {
        "metadata": {
            "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "version": "1.0",
            "format": "finmind_backup",
            "tables": list(data.keys()),
            "record_count": {k: len(v) for k, v in data.items()},
        },
        "data": data,
    }
    return json.dumps(payload, default=_serialize_value, indent=2, ensure_ascii=False)


def export_to_csv(data: dict[str, list[dict]]) -> str:
    """Export structured data as a single multi-section CSV.

    Each table gets a header section followed by its rows.
    Returns a single CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    for table_name, rows in data.items():
        writer.writerow([f"=== {table_name} ==="])
        if rows:
            headers = list(rows[0].keys())
            writer.writerow(headers)
            for row in rows:
                writer.writerow([_serialize_value(row.get(h)) for h in headers])
        writer.writerow([])  # blank separator

    return output.getvalue()


def build_export_data(user_id: int, db_session) -> dict[str, list[dict]]:
    """Query all user data and return as serializable dicts.

    Imports are done locally to avoid circular imports.
    """
    from app.models import (
        Expense,
        Category,
        Bill,
        RecurringExpense,
        Reminder,
        UserSubscription,
    )

    tables: dict[str, list[dict]] = {}

    # User profile (without password_hash)
    user = db_session.query(User).get(user_id)
    if user:
        tables["user"] = [
            {
                "id": user.id,
                "email": user.email,
                "preferred_currency": user.preferred_currency,
                "role": user.role,
                "created_at": _serialize_value(user.created_at),
            }
        ]

    # Categories
    cats = db_session.query(Category).filter_by(user_id=user_id).all()
    tables["categories"] = [
        {"id": c.id, "name": c.name, "created_at": _serialize_value(c.created_at)}
        for c in cats
    ]

    # Expenses
    exps = db_session.query(Expense).filter_by(user_id=user_id).all()
    tables["expenses"] = [
        {
            "id": e.id,
            "category_id": e.category_id,
            "amount": _serialize_value(e.amount),
            "currency": e.currency,
            "expense_type": e.expense_type,
            "notes": e.notes,
            "spent_at": _serialize_value(e.spent_at),
            "created_at": _serialize_value(e.created_at),
        }
        for e in exps
    ]

    # Bills
    bills = db_session.query(Bill).filter_by(user_id=user_id).all()
    tables["bills"] = [
        {
            "id": b.id,
            "name": b.name,
            "amount": _serialize_value(b.amount),
            "currency": b.currency,
            "next_due_date": _serialize_value(b.next_due_date),
            "cadence": b.cadence.value if b.cadence else None,
            "autopay_enabled": b.autopay_enabled,
            "active": b.active,
            "created_at": _serialize_value(b.created_at),
        }
        for b in bills
    ]

    # Recurring expenses
    recs = db_session.query(RecurringExpense).filter_by(user_id=user_id).all()
    tables["recurring_expenses"] = [
        {
            "id": r.id,
            "category_id": r.category_id,
            "amount": _serialize_value(r.amount),
            "currency": r.currency,
            "expense_type": r.expense_type,
            "notes": r.notes,
            "cadence": r.cadence.value if r.cadence else None,
            "start_date": _serialize_value(r.start_date),
            "end_date": _serialize_value(r.end_date),
            "active": r.active,
        }
        for r in recs
    ]

    # Reminders
    rems = db_session.query(Reminder).filter_by(user_id=user_id).all()
    tables["reminders"] = [
        {
            "id": rm.id,
            "bill_id": rm.bill_id,
            "message": rm.message,
            "send_at": _serialize_value(rm.send_at),
            "sent": rm.sent,
            "channel": rm.channel,
        }
        for rm in rems
    ]

    return tables


def encrypt_export(data_json: str, passphrase: str) -> dict:
    """Encrypt a JSON export string and return metadata + base64 payload.

    Returns dict with salt, encrypted_data (base64), format info.
    """
    encrypted = encrypt_data(data_json.encode("utf-8"), passphrase)
    return {
        "format": "aes-256-gcm",
        "encrypted_data": base64.b64encode(encrypted).decode("ascii"),
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def decrypt_export(encrypted_b64: str, passphrase: str) -> str:
    """Decrypt a base64-encoded encrypted payload back to JSON string."""
    encrypted = base64.b64decode(encrypted_b64)
    decrypted = decrypt_data(encrypted, passphrase)
    return decrypted.decode("utf-8")
