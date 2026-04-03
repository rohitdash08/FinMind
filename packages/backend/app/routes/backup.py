import base64
import csv
import hashlib
import io
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import (
    Bill,
    Category,
    Expense,
    RecurringExpense,
    User,
)

bp = Blueprint("backup", __name__)
logger = logging.getLogger("finmind.backup")

_PBKDF2_ITERATIONS = 600_000
_SALT_BYTES = 16
_NONCE_BYTES = 12
_BACKUP_FORMAT_VERSION = 1
_MIN_PASSWORD_LENGTH = 8


# ---------------------------------------------------------------------------
# Crypto helpers
# ---------------------------------------------------------------------------


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit key from *password* using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt(plaintext: bytes, password: str) -> dict:
    """Encrypt *plaintext* with AES-256-GCM and return envelope dict."""
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    key = _derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return {
        "version": _BACKUP_FORMAT_VERSION,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "kdf": "pbkdf2-sha256",
        "kdf_iterations": _PBKDF2_ITERATIONS,
        "cipher": "aes-256-gcm",
    }


def _decrypt(envelope: dict, password: str) -> bytes:
    """Decrypt an envelope dict and return the plaintext bytes.

    Raises ``ValueError`` on any decryption or format error.
    """
    try:
        salt = base64.b64decode(envelope["salt"])
        nonce = base64.b64decode(envelope["nonce"])
        ciphertext = base64.b64decode(envelope["ciphertext"])
    except (KeyError, Exception) as exc:
        raise ValueError(f"malformed backup envelope: {exc}") from exc

    key = _derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError("decryption failed – wrong password or corrupted data") from exc


# ---------------------------------------------------------------------------
# Data serialisation helpers
# ---------------------------------------------------------------------------


class _BackupEncoder(json.JSONEncoder):
    """Handle Decimal, date, and datetime when serialising backup data."""

    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        return super().default(o)


def _gather_user_data(uid: int) -> dict:
    """Collect all exportable data for the given user."""
    user = db.session.get(User, uid)
    categories = (
        db.session.query(Category).filter_by(user_id=uid).order_by(Category.id).all()
    )
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .all()
    )
    recurring = (
        db.session.query(RecurringExpense)
        .filter_by(user_id=uid)
        .order_by(RecurringExpense.id)
        .all()
    )
    bills = (
        db.session.query(Bill).filter_by(user_id=uid).order_by(Bill.id).all()
    )

    return {
        "exported_at": datetime.utcnow().isoformat(),
        "user": {
            "email": user.email if user else None,
            "preferred_currency": user.preferred_currency if user else "INR",
        },
        "categories": [
            {"id": c.id, "name": c.name} for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "amount": e.amount,
                "currency": e.currency,
                "expense_type": e.expense_type,
                "category_id": e.category_id,
                "description": e.notes or "",
                "date": e.spent_at,
            }
            for e in expenses
        ],
        "recurring_expenses": [
            {
                "id": r.id,
                "amount": r.amount,
                "currency": r.currency,
                "expense_type": r.expense_type,
                "category_id": r.category_id,
                "description": r.notes,
                "cadence": r.cadence.value,
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
                "cadence": b.cadence.value,
                "autopay_enabled": b.autopay_enabled,
                "active": b.active,
            }
            for b in bills
        ],
    }


def _expenses_to_csv(expenses: list[dict]) -> str:
    """Convert expense dicts to CSV string."""
    buf = io.StringIO()
    fieldnames = [
        "id",
        "amount",
        "currency",
        "expense_type",
        "category_id",
        "description",
        "date",
    ]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for exp in expenses:
        row = {k: exp.get(k, "") for k in fieldnames}
        if isinstance(row.get("amount"), Decimal):
            row["amount"] = float(row["amount"])
        if isinstance(row.get("date"), (date, datetime)):
            row["date"] = row["date"].isoformat()
        writer.writerow(row)
    return buf.getvalue()


def _validate_password(password: str | None) -> str | None:
    """Return an error message if *password* is invalid, else ``None``."""
    if not password or not isinstance(password, str):
        return "backup_password is required"
    if len(password) < _MIN_PASSWORD_LENGTH:
        return f"backup_password must be at least {_MIN_PASSWORD_LENGTH} characters"
    return None


# ---------------------------------------------------------------------------
# In-memory backup history (per-process; swap for DB/Redis in production)
# ---------------------------------------------------------------------------

_backup_history: dict[int, list[dict]] = {}


def _record_backup(uid: int, *, format_type: str, record_count: int) -> dict:
    entry = {
        "id": len(_backup_history.get(uid, [])) + 1,
        "format": format_type,
        "record_count": record_count,
        "created_at": datetime.utcnow().isoformat(),
    }
    _backup_history.setdefault(uid, []).append(entry)
    return entry


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@bp.post("/export")
@jwt_required()
def export_json():
    """Export all user data as AES-256-GCM encrypted JSON."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("backup_password")

    err = _validate_password(password)
    if err:
        return jsonify(error=err), 400

    user_data = _gather_user_data(uid)
    plaintext = json.dumps(user_data, cls=_BackupEncoder).encode("utf-8")
    envelope = _encrypt(plaintext, password)

    record_count = len(user_data["expenses"])
    _record_backup(uid, format_type="json", record_count=record_count)

    logger.info(
        "Exported JSON backup user=%s expenses=%s", uid, record_count
    )
    return jsonify(backup=envelope), 200


@bp.post("/export/csv")
@jwt_required()
def export_csv():
    """Export expenses as AES-256-GCM encrypted CSV."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("backup_password")

    err = _validate_password(password)
    if err:
        return jsonify(error=err), 400

    user_data = _gather_user_data(uid)
    csv_text = _expenses_to_csv(user_data["expenses"])
    plaintext = csv_text.encode("utf-8")
    envelope = _encrypt(plaintext, password)

    record_count = len(user_data["expenses"])
    _record_backup(uid, format_type="csv", record_count=record_count)

    logger.info(
        "Exported CSV backup user=%s expenses=%s", uid, record_count
    )
    return jsonify(backup=envelope), 200


@bp.post("/import")
@jwt_required()
def import_backup():
    """Import and decrypt an encrypted JSON backup.

    Merges categories (by name) and inserts expenses that don't already exist.
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("backup_password")
    envelope = data.get("backup")

    err = _validate_password(password)
    if err:
        return jsonify(error=err), 400

    if not envelope or not isinstance(envelope, dict):
        return jsonify(error="backup payload is required"), 400

    try:
        plaintext = _decrypt(envelope, password)
    except ValueError as exc:
        logger.warning("Import decrypt failed user=%s: %s", uid, exc)
        return jsonify(error=str(exc)), 400

    try:
        backup_data = json.loads(plaintext)
    except json.JSONDecodeError:
        return jsonify(error="decrypted data is not valid JSON"), 400

    imported_categories = 0
    imported_expenses = 0
    skipped_expenses = 0

    # --- categories ---
    existing_categories = {
        c.name: c.id
        for c in db.session.query(Category).filter_by(user_id=uid).all()
    }
    cat_id_map: dict[int | None, int | None] = {None: None}

    for cat in backup_data.get("categories", []):
        name = cat.get("name", "").strip()
        if not name:
            continue
        if name in existing_categories:
            cat_id_map[cat.get("id")] = existing_categories[name]
        else:
            new_cat = Category(user_id=uid, name=name)
            db.session.add(new_cat)
            db.session.flush()
            existing_categories[name] = new_cat.id
            cat_id_map[cat.get("id")] = new_cat.id
            imported_categories += 1

    # --- expenses ---
    for exp in backup_data.get("expenses", []):
        description = (exp.get("description") or "").strip()
        if not description:
            continue
        spent_at = date.fromisoformat(exp["date"])
        amount = Decimal(str(exp["amount"])).quantize(Decimal("0.01"))

        duplicate = (
            db.session.query(Expense)
            .filter_by(
                user_id=uid,
                spent_at=spent_at,
                amount=amount,
                notes=description,
            )
            .first()
        )
        if duplicate:
            skipped_expenses += 1
            continue

        mapped_cat = cat_id_map.get(exp.get("category_id"))
        new_expense = Expense(
            user_id=uid,
            amount=amount,
            currency=exp.get("currency", "INR"),
            expense_type=exp.get("expense_type", "EXPENSE"),
            category_id=mapped_cat,
            notes=description,
            spent_at=spent_at,
        )
        db.session.add(new_expense)
        imported_expenses += 1

    db.session.commit()

    logger.info(
        "Imported backup user=%s categories=%s expenses=%s skipped=%s",
        uid,
        imported_categories,
        imported_expenses,
        skipped_expenses,
    )
    return jsonify(
        imported_categories=imported_categories,
        imported_expenses=imported_expenses,
        skipped_duplicates=skipped_expenses,
    ), 200


@bp.get("/history")
@jwt_required()
def backup_history():
    """List past backup operations for the current user."""
    uid = int(get_jwt_identity())
    entries = list(reversed(_backup_history.get(uid, [])))
    return jsonify(entries), 200
