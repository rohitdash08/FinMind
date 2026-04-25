import base64
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ..extensions import db
from ..models import Bill, Category, Expense, RecurringExpense, Reminder, User

BACKUP_SCHEMA_VERSION = "finmind.secure-backup.v1"
KDF_NAME = "PBKDF2-HMAC-SHA256"
KDF_ITERATIONS = 390_000
MIN_PASSPHRASE_LENGTH = 12


class BackupPassphraseError(ValueError):
    pass


class BackupDecryptError(ValueError):
    pass


def export_user_backup(user_id: int, passphrase: str) -> dict[str, Any]:
    """Build and encrypt a complete user-owned financial backup."""
    _validate_passphrase(passphrase)
    backup = _build_backup_payload(user_id)
    plaintext = json.dumps(backup, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    salt = os.urandom(16)
    fernet = Fernet(_derive_fernet_key(passphrase, salt, KDF_ITERATIONS))
    token = fernet.encrypt(plaintext).decode("ascii")
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "encrypted": True,
        "algorithm": "Fernet-AES128-CBC-HMAC-SHA256",
        "kdf": KDF_NAME,
        "iterations": KDF_ITERATIONS,
        "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
        "ciphertext": token,
        "plaintext_sha256": sha256(plaintext).hexdigest(),
        "record_counts": backup["record_counts"],
        "exported_at": backup["exported_at"],
    }


def decrypt_backup(envelope: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Decrypt a backup envelope. Intended for tests and future import flows."""
    try:
        salt = base64.urlsafe_b64decode(envelope["salt"].encode("ascii"))
        iterations = int(envelope.get("iterations") or KDF_ITERATIONS)
        ciphertext = str(envelope["ciphertext"]).encode("ascii")
    except (KeyError, TypeError, ValueError) as exc:
        raise BackupDecryptError("invalid backup envelope") from exc
    try:
        plaintext = Fernet(_derive_fernet_key(passphrase, salt, iterations)).decrypt(
            ciphertext
        )
    except InvalidToken as exc:
        raise BackupDecryptError("invalid passphrase or tampered backup") from exc
    digest = envelope.get("plaintext_sha256")
    if digest and sha256(plaintext).hexdigest() != digest:
        raise BackupDecryptError("backup digest mismatch")
    return json.loads(plaintext.decode("utf-8"))


def _build_backup_payload(user_id: int) -> dict[str, Any]:
    user = db.session.get(User, user_id)
    if not user:
        raise LookupError("user not found")

    categories = db.session.query(Category).filter_by(user_id=user_id).all()
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
    recurring = db.session.query(RecurringExpense).filter_by(user_id=user_id).all()
    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    reminders = db.session.query(Reminder).filter_by(user_id=user_id).all()

    records = {
        "categories": [
            _model_dict(c, ["id", "name", "created_at"]) for c in categories
        ],
        "expenses": [
            _model_dict(
                e,
                [
                    "id",
                    "category_id",
                    "amount",
                    "currency",
                    "expense_type",
                    "notes",
                    "spent_at",
                    "source_recurring_id",
                    "created_at",
                ],
            )
            for e in expenses
        ],
        "recurring_expenses": [
            _model_dict(
                r,
                [
                    "id",
                    "category_id",
                    "amount",
                    "currency",
                    "expense_type",
                    "notes",
                    "cadence",
                    "start_date",
                    "end_date",
                    "active",
                    "created_at",
                ],
            )
            for r in recurring
        ],
        "bills": [
            _model_dict(
                b,
                [
                    "id",
                    "name",
                    "amount",
                    "currency",
                    "next_due_date",
                    "cadence",
                    "autopay_enabled",
                    "channel_whatsapp",
                    "channel_email",
                    "active",
                    "created_at",
                ],
            )
            for b in bills
        ],
        "reminders": [
            _model_dict(r, ["id", "bill_id", "message", "send_at", "sent", "channel"])
            for r in reminders
        ],
    }
    return {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "created_at": _json_value(user.created_at),
        },
        "records": records,
        "record_counts": {name: len(items) for name, items in records.items()},
    }


def _derive_fernet_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    ).derive(passphrase.encode("utf-8"))
    return base64.urlsafe_b64encode(key)


def _validate_passphrase(passphrase: str) -> None:
    if not isinstance(passphrase, str) or len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise BackupPassphraseError(
            f"passphrase must be at least {MIN_PASSPHRASE_LENGTH} characters"
        )


def _model_dict(model: Any, fields: list[str]) -> dict[str, Any]:
    return {field: _json_value(getattr(model, field)) for field in fields}


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    return value
