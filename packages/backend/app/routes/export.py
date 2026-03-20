"""Secure encrypted export of user data (Issue #126)."""

import csv
import io
import json
import logging
import os
import base64
from datetime import date

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Expense, Bill, Category

bp = Blueprint("export", __name__)
logger = logging.getLogger("finmind.export")

PBKDF2_ITERATIONS = 480_000


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 256-bit AES key from a password using PBKDF2-HMAC-SHA256."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def _encrypt_aes_gcm(plaintext: bytes, password: str) -> dict:
    """Encrypt plaintext with AES-256-GCM using a password-derived key.

    Returns a dict with base64-encoded salt, nonce, and ciphertext.
    """
    salt = os.urandom(16)
    key = _derive_key(password, salt)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return {
        "algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-HMAC-SHA256",
        "iterations": PBKDF2_ITERATIONS,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }


def _collect_user_data(uid: int) -> dict:
    """Gather all exportable user data."""
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=uid)
        .order_by(Expense.spent_at.desc())
        .all()
    )
    bills = (
        db.session.query(Bill)
        .filter_by(user_id=uid)
        .order_by(Bill.created_at.desc())
        .all()
    )
    categories = (
        db.session.query(Category)
        .filter_by(user_id=uid)
        .order_by(Category.name)
        .all()
    )

    return {
        "exported_at": date.today().isoformat(),
        "expenses": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "category_id": e.category_id,
                "description": e.notes or "",
                "date": e.spent_at.isoformat(),
            }
            for e in expenses
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
                "active": b.active,
            }
            for b in bills
        ],
        "categories": [
            {"id": c.id, "name": c.name}
            for c in categories
        ],
    }


def _data_to_csv(data: dict) -> str:
    """Flatten user data into a CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)

    # Expenses
    writer.writerow(["[expenses]"])
    writer.writerow(["id", "amount", "currency", "expense_type", "category_id", "description", "date"])
    for e in data["expenses"]:
        writer.writerow([e["id"], e["amount"], e["currency"], e["expense_type"],
                         e["category_id"], e["description"], e["date"]])

    writer.writerow([])
    writer.writerow(["[bills]"])
    writer.writerow(["id", "name", "amount", "currency", "next_due_date", "cadence", "active"])
    for b in data["bills"]:
        writer.writerow([b["id"], b["name"], b["amount"], b["currency"],
                         b["next_due_date"], b["cadence"], b["active"]])

    writer.writerow([])
    writer.writerow(["[categories]"])
    writer.writerow(["id", "name"])
    for c in data["categories"]:
        writer.writerow([c["id"], c["name"]])

    return buf.getvalue()


@bp.post("")
@jwt_required()
def export_data():
    """Export user data as encrypted JSON or CSV.

    Request body:
        password (str): encryption password (min 8 chars)
        format (str): "json" or "csv" (default "json")
    """
    uid = int(get_jwt_identity())
    body = request.get_json() or {}
    password = (body.get("password") or "").strip()
    fmt = (body.get("format") or "json").strip().lower()

    if not password or len(password) < 8:
        return jsonify(error="password must be at least 8 characters"), 400
    if fmt not in ("json", "csv"):
        return jsonify(error="format must be 'json' or 'csv'"), 400

    data = _collect_user_data(uid)

    if fmt == "csv":
        plaintext = _data_to_csv(data).encode("utf-8")
    else:
        plaintext = json.dumps(data, indent=2).encode("utf-8")

    encrypted = _encrypt_aes_gcm(plaintext, password)
    encrypted["format"] = fmt

    logger.info("Exported data user=%s format=%s", uid, fmt)
    return jsonify(encrypted), 200
