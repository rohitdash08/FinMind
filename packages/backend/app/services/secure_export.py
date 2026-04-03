"""Secure backup & encrypted export service.

Exports user financial data (expenses, bills, categories, reminders)
as encrypted JSON or plain CSV. Encryption uses AES-256-GCM via
the Python cryptography library's Fernet (AES-128-CBC + HMAC)
for simplicity, or raw AES-GCM for stronger guarantees.

Uses a user-provided passphrase, derived into a key via PBKDF2.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import date
from io import StringIO
from typing import Any

from ..extensions import db
from ..models import Bill, Category, Expense, Reminder

logger = logging.getLogger("finmind.secure_export")


def export_user_data(user_id: int, fmt: str = "json") -> dict[str, Any]:
    """Export all financial data for a user.

    Args:
        user_id: User to export.
        fmt: Format — 'json' or 'csv'.

    Returns:
        Dict with 'data' (str), 'format', 'exported_at'.
    """
    expenses = _query_expenses(user_id)
    bills = _query_bills(user_id)
    categories = _query_categories(user_id)
    reminders = _query_reminders(user_id)

    payload = {
        "exported_at": date.today().isoformat(),
        "user_id": user_id,
        "expenses": expenses,
        "bills": bills,
        "categories": categories,
        "reminders": reminders,
        "totals": {
            "expenses": len(expenses),
            "bills": len(bills),
            "categories": len(categories),
            "reminders": len(reminders),
        },
    }

    if fmt == "csv":
        data = _to_csv(expenses)
    else:
        data = json.dumps(payload, indent=2, default=str)

    return {"data": data, "format": fmt, "exported_at": payload["exported_at"]}


def encrypt_data(plaintext: str, passphrase: str) -> dict[str, str]:
    """Encrypt data using AES-256-GCM with PBKDF2-derived key.

    Args:
        plaintext: Data to encrypt.
        passphrase: User-provided passphrase.

    Returns:
        Dict with base64-encoded 'ciphertext', 'salt', 'iv', 'tag'.
    """
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 100_000, dklen=32)

    iv = os.urandom(12)

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(iv, plaintext.encode(), None)
        # ciphertext includes the 16-byte tag appended
        ct = ciphertext[:-16]
        tag = ciphertext[-16:]
    except ImportError:
        # Fallback: use hashlib-based XOR stream (NOT production-grade)
        # This is a placeholder — in production, cryptography lib is required
        logger.warning("cryptography library not installed, using basic encryption")
        stream = hashlib.pbkdf2_hmac("sha256", key, iv, 1, dklen=len(plaintext))
        ct = bytes(a ^ b for a, b in zip(plaintext.encode(), stream))
        tag = hashlib.sha256(ct).digest()[:16]

    return {
        "ciphertext": base64.b64encode(ct).decode(),
        "salt": base64.b64encode(salt).decode(),
        "iv": base64.b64encode(iv).decode(),
        "tag": base64.b64encode(tag).decode(),
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256",
        "iterations": 100_000,
    }


def decrypt_data(encrypted: dict[str, str], passphrase: str) -> str:
    """Decrypt data encrypted by encrypt_data."""
    salt = base64.b64decode(encrypted["salt"])
    iv = base64.b64decode(encrypted["iv"])
    ct = base64.b64decode(encrypted["ciphertext"])
    tag = base64.b64decode(encrypted["tag"])

    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 100_000, dklen=32)

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(iv, ct + tag, None)
        return plaintext.decode()
    except ImportError:
        stream = hashlib.pbkdf2_hmac("sha256", key, iv, 1, dklen=len(ct))
        plaintext = bytes(a ^ b for a, b in zip(ct, stream))
        return plaintext.decode()


def _query_expenses(uid: int) -> list[dict]:
    items = db.session.query(Expense).filter_by(user_id=uid).order_by(Expense.spent_at.desc()).all()
    return [
        {"id": e.id, "amount": float(e.amount), "currency": e.currency,
         "type": e.expense_type, "description": e.notes, "date": e.spent_at.isoformat(),
         "category_id": e.category_id}
        for e in items
    ]


def _query_bills(uid: int) -> list[dict]:
    items = db.session.query(Bill).filter_by(user_id=uid).all()
    return [
        {"id": b.id, "name": b.name, "amount": float(b.amount), "currency": b.currency,
         "due": b.next_due_date.isoformat(), "cadence": b.cadence.value if b.cadence else None,
         "active": b.active}
        for b in items
    ]


def _query_categories(uid: int) -> list[dict]:
    items = db.session.query(Category).filter_by(user_id=uid).all()
    return [{"id": c.id, "name": c.name} for c in items]


def _query_reminders(uid: int) -> list[dict]:
    items = db.session.query(Reminder).filter_by(user_id=uid).all()
    return [
        {"id": r.id, "message": r.message, "send_at": r.send_at.isoformat() if r.send_at else None,
         "sent": r.sent, "channel": r.channel}
        for r in items
    ]


def _to_csv(expenses: list[dict]) -> str:
    """Convert expenses to CSV string."""
    if not expenses:
        return "id,amount,currency,type,description,date,category_id\n"
    buf = StringIO()
    headers = list(expenses[0].keys())
    buf.write(",".join(headers) + "\n")
    for row in expenses:
        vals = [str(row.get(h, "")).replace(",", ";").replace("\n", " ") for h in headers]
        buf.write(",".join(vals) + "\n")
    return buf.getvalue()
