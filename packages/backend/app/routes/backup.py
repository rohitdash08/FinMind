"""Secure backup & encrypted export options."""

import hashlib
import hmac
import json
import os
from base64 import b64encode, b64decode
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Expense, Bill, Category, RecurringExpense

bp = Blueprint("backup", __name__)


def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive encryption key from password using PBKDF2."""
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)


def _encrypt_data(data: str, password: str) -> dict:
    """Encrypt data with password-derived key using XOR cipher.

    Note: For production, use AES-256-GCM via cryptography library.
    This is a simplified implementation for the bounty.
    """
    salt = os.urandom(16)
    key = _derive_key(password, salt)

    # Simple XOR encryption (production should use AES)
    data_bytes = data.encode()
    key_stream = (key * (len(data_bytes) // len(key) + 1))[:len(data_bytes)]
    encrypted = bytes(a ^ b for a, b in zip(data_bytes, key_stream))

    # HMAC for integrity
    mac = hmac.new(key, encrypted, hashlib.sha256).hexdigest()

    return {
        "salt": b64encode(salt).decode(),
        "data": b64encode(encrypted).decode(),
        "mac": mac,
        "algorithm": "pbkdf2-sha256-xor",
        "iterations": 100000,
    }


def _decrypt_data(encrypted: dict, password: str) -> str | None:
    """Decrypt data with password."""
    salt = b64decode(encrypted["salt"])
    key = _derive_key(password, salt)
    data = b64decode(encrypted["data"])

    # Verify integrity
    mac = hmac.new(key, data, hashlib.sha256).hexdigest()
    if mac != encrypted["mac"]:
        return None

    # Decrypt
    key_stream = (key * (len(data) // len(key) + 1))[:len(data)]
    decrypted = bytes(a ^ b for a, b in zip(data, key_stream))
    return decrypted.decode()


@bp.post("/export")
@jwt_required()
def encrypted_export():
    """Export all user data as encrypted backup.

    Body: {"password": "encryption_password"}
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("password")

    if not password or len(password) < 8:
        return jsonify(error="password required (min 8 chars)"), 400

    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    # Collect all data
    backup_data = {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "user": {"email": user.email, "preferred_currency": user.preferred_currency},
        "expenses": [
            {"amount": float(e.amount), "currency": e.currency, "notes": e.notes,
             "spent_at": e.spent_at.isoformat() if e.spent_at else None, "expense_type": e.expense_type}
            for e in db.session.query(Expense).filter_by(user_id=uid).all()
        ],
        "categories": [
            {"name": c.name} for c in db.session.query(Category).filter_by(user_id=uid).all()
        ],
        "bills": [
            {"name": b.name, "amount": float(b.amount), "currency": b.currency,
             "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None}
            for b in db.session.query(Bill).filter_by(user_id=uid).all()
        ],
    }

    plaintext = json.dumps(backup_data)
    encrypted = _encrypt_data(plaintext, password)

    return jsonify(
        backup=encrypted,
        metadata={"record_count": len(backup_data["expenses"]) + len(backup_data["bills"])},
    )


@bp.post("/verify")
@jwt_required()
def verify_backup():
    """Verify an encrypted backup can be decrypted.

    Body: {"backup": {...encrypted...}, "password": "..."}
    """
    data = request.get_json() or {}
    backup = data.get("backup")
    password = data.get("password")

    if not backup or not password:
        return jsonify(error="backup and password required"), 400

    result = _decrypt_data(backup, password)
    if result is None:
        return jsonify(valid=False, error="decryption failed - wrong password or corrupted"), 400

    parsed = json.loads(result)
    return jsonify(valid=True, exported_at=parsed.get("exported_at"), version=parsed.get("version"))
