"""
export.py — Secure backup and encrypted data export service.

Exports all user financial data as:
  - JSON (structured, all tables)
  - CSV (one file per table, bundled as ZIP)

Optional AES-256 encryption via Fernet (cryptography library).
Passphrase-based key derivation via PBKDF2-HMAC-SHA256.

Public API:
    export_user_json(uid, session) -> bytes          (UTF-8 JSON)
    export_user_csv_zip(uid, session) -> bytes       (ZIP archive)
    encrypt_payload(data: bytes, passphrase: str) -> bytes
    decrypt_payload(data: bytes, passphrase: str) -> bytes
"""
from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import zipfile
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from ..models import (
    Bill,
    Category,
    Expense,
    RecurringExpense,
    Reminder,
    User,
)

logger = logging.getLogger("finmind.export")

_PBKDF2_ITERATIONS = 390_000  # OWASP recommended minimum (2023)
_SALT_LENGTH = 32  # bytes


def _json_default(obj):
    """JSON serialiser for dates and Decimals."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Not serialisable: {type(obj)}")


def _collect_user_data(uid: int, session: Session) -> dict:
    """Pull all user data into a serialisable dict."""
    user = session.get(User, uid)
    if not user:
        return {}

    categories = session.query(Category).filter_by(user_id=uid).all()
    expenses = (
        session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at)
        .all()
    )
    recurring = session.query(RecurringExpense).filter_by(user_id=uid).all()
    bills = session.query(Bill).filter_by(user_id=uid).all()
    reminders = session.query(Reminder).filter_by(user_id=uid).all()

    return {
        "export_version": "1.0",
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
        },
        "categories": [
            {"id": c.id, "name": c.name, "created_at": c.created_at}
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": e.amount,
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at,
                "created_at": e.created_at,
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "category_id": r.category_id,
                "amount": r.amount,
                "currency": r.currency,
                "cadence": r.cadence.value if hasattr(r.cadence, "value") else r.cadence,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "active": r.active,
            }
            for r in recurring
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": b.amount,
                "currency": b.currency,
                "next_due_date": b.next_due_date,
                "cadence": b.cadence.value if hasattr(b.cadence, "value") else b.cadence,
                "active": b.active,
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": r.id,
                "bill_id": r.bill_id,
                "message": r.message,
                "send_at": r.send_at,
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in reminders
        ],
    }


def export_user_json(uid: int, session: Session) -> bytes:
    """Return user data as UTF-8 JSON bytes."""
    data = _collect_user_data(uid, session)
    return json.dumps(data, default=_json_default, indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


def export_user_csv_zip(uid: int, session: Session) -> bytes:
    """Return a ZIP archive containing one CSV file per data table."""
    data = _collect_user_data(uid, session)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for table_name, rows in data.items():
            if not isinstance(rows, list) or not rows:
                continue
            csv_buf = io.StringIO()
            writer = csv.DictWriter(csv_buf, fieldnames=rows[0].keys())
            writer.writeheader()
            for row in rows:
                # Flatten non-primitive objects to strings
                flat = {
                    k: str(v)
                    if not isinstance(v, (str, int, float, bool, type(None)))
                    else v
                    for k, v in row.items()
                }
                writer.writerow(flat)
            zf.writestr(f"{table_name}.csv", csv_buf.getvalue())

    buf.seek(0)
    return buf.read()


def encrypt_payload(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt bytes with AES-256 (Fernet) using PBKDF2 key derivation.

    Output format: base64(salt + fernet_token)
    The salt is prepended so decryption can re-derive the key.
    """
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    salt = os.urandom(_SALT_LENGTH)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    token = Fernet(key).encrypt(data)
    # Prepend salt so we can decrypt later
    return base64.b64encode(salt + token)


def decrypt_payload(data: bytes, passphrase: str) -> bytes:
    """Decrypt a payload produced by encrypt_payload()."""
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    raw = base64.b64decode(data)
    salt = raw[:_SALT_LENGTH]
    token = raw[_SALT_LENGTH:]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
    return Fernet(key).decrypt(token)
