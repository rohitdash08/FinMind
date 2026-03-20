from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import date, timedelta
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func

from app.models import Transaction
from app import db


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EncryptedExport:
    export_id: str              # random UUID-like ID for reference
    encrypted_data: str         # base64-encoded encrypted payload
    checksum: str               # SHA-256 of the original plaintext
    record_count: int
    encryption_hint: str        # "AES-256 password-based" or similar
    created_at: str             # ISO date


@dataclass
class ExportResult:
    export: EncryptedExport
    summary: str


# ---------------------------------------------------------------------------
# Simple XOR + base64 encryption (password-based, no external deps)
# In production: replace with PyCryptodome AES-256-GCM
# ---------------------------------------------------------------------------

def _derive_key(password: str, salt: bytes) -> bytes:
    """Derive a 32-byte key from password using PBKDF2."""
    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        iterations=100_000,
        dklen=32,
    )


def _xor_encrypt(data: bytes, key: bytes) -> bytes:
    """XOR cipher (simple, no external deps). Key is repeated cyclically."""
    key_bytes = key * (len(data) // len(key) + 1)
    return bytes(a ^ b for a, b in zip(data, key_bytes[:len(data)]))


def encrypt_data(plaintext: str, password: str) -> tuple[str, str]:
    """
    Encrypt plaintext with password. Returns (base64_ciphertext, checksum).
    Uses PBKDF2 key derivation + XOR cipher with salt prepended.
    """
    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt)
    data_bytes = plaintext.encode('utf-8')
    checksum = hashlib.sha256(data_bytes).hexdigest()
    cipher = _xor_encrypt(data_bytes, key)
    # Prepend salt to ciphertext for decryption
    combined = salt + cipher
    return base64.b64encode(combined).decode('utf-8'), checksum


def decrypt_data(base64_ciphertext: str, password: str) -> str:
    """
    Decrypt data encrypted with encrypt_data. Returns plaintext.
    Raises ValueError on wrong password (checksum mismatch detectable by caller).
    """
    combined = base64.b64decode(base64_ciphertext.encode('utf-8'))
    salt = combined[:16]
    cipher = combined[16:]
    key = _derive_key(password, salt)
    plaintext_bytes = _xor_encrypt(cipher, key)
    return plaintext_bytes.decode('utf-8')


# ---------------------------------------------------------------------------
# Export service
# ---------------------------------------------------------------------------

def create_encrypted_export(
    user_id: int,
    password: str,
    months: int = 12,
    include_categories: Optional[list[str]] = None,
) -> ExportResult:
    """
    Export user transactions as an encrypted backup.

    Args:
        user_id: JWT user id
        password: encryption password
        months: how many months of history to export (1-60)
        include_categories: optional category filter (None = all)
    """
    months = max(1, min(60, months))
    cutoff = date.today() - timedelta(days=months * 31)

    query = db.session.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.date >= cutoff,
    )

    if include_categories:
        query = query.filter(Transaction.category.in_(include_categories))

    transactions = query.all()

    # Serialize to JSON
    records = []
    for tx in transactions:
        try:
            tx_date = tx.date.isoformat() if isinstance(tx.date, date) else str(tx.date)
        except AttributeError:
            tx_date = str(tx.date)

        records.append({
            "id": tx.id,
            "date": tx_date,
            "amount": float(tx.amount or 0),
            "type": tx.type,
            "category": tx.category or "",
            "description": tx.description or "",
        })

    export_data = {
        "version": "1.0",
        "exported_at": date.today().isoformat(),
        "user_id": user_id,
        "record_count": len(records),
        "transactions": records,
    }

    plaintext = json.dumps(export_data, separators=(',', ':'))
    encrypted, checksum = encrypt_data(plaintext, password)

    export_id = secrets.token_hex(16)
    export = EncryptedExport(
        export_id=export_id,
        encrypted_data=encrypted,
        checksum=checksum,
        record_count=len(records),
        encryption_hint="PBKDF2+XOR-256 (upgrade to AES-256-GCM in production)",
        created_at=date.today().isoformat(),
    )

    summary = (
        f"Exported {len(records)} transactions from the past {months} months. "
        f"Encrypted with password-based key derivation (PBKDF2, 100K iterations). "
        f"SHA-256 checksum: {checksum[:12]}..."
    )

    return ExportResult(export=export, summary=summary)