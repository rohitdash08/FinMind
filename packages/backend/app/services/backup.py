import json
import os
import logging
import hashlib
from datetime import datetime, timedelta
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.backends import default_backend

from ..extensions import db
from ..models import BackupExport, Expense, Bill, Reminder, Category, User

logger = logging.getLogger("finmind.backup")

ENCRYPTION_ALGO = "aes-256-gcm"
KEY_DERIVATION = "sha256-pbkdf2"


def _derive_key(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 600000, dklen=32)
    return key, salt


def _encrypt(plaintext: str, password: str) -> dict:
    key, salt = _derive_key(password)
    iv = os.urandom(12)
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext.encode("utf-8")) + padder.finalize()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    return {
        "ciphertext": ciphertext.hex(),
        "iv": iv.hex(),
        "tag": encryptor.tag.hex(),
        "salt": salt.hex(),
        "algo": ENCRYPTION_ALGO,
        "kdf": KEY_DERIVATION,
    }


def _decrypt(encrypted: dict, password: str) -> str:
    key, _ = _derive_key(password, bytes.fromhex(encrypted["salt"]))
    iv = bytes.fromhex(encrypted["iv"])
    tag = bytes.fromhex(encrypted["tag"])
    ciphertext = bytes.fromhex(encrypted["ciphertext"])
    cipher = Cipher(algorithms.AES(key), modes.GCM(iv, tag), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded_data) + unpadder.finalize()).decode("utf-8")


def _password_hash(password: str, salt: bytes | None = None) -> tuple[str, str]:
    if salt is None:
        salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000, dklen=32)
    return h.hex(), salt.hex()


def _verify_password(password: str, stored_hash: str, stored_salt_hex: str) -> bool:
    h, _ = _password_hash(password, bytes.fromhex(stored_salt_hex))
    return h == stored_hash


def _collect_user_data(user_id: int) -> dict:
    expenses = Expense.query.filter(Expense.user_id == user_id).all()
    bills = Bill.query.filter(Bill.user_id == user_id).all()
    reminders = Reminder.query.filter(Reminder.user_id == user_id).all()
    categories = Category.query.filter(Category.user_id == user_id).all()
    user = User.query.get(user_id)
    return {
        "version": "1.0",
        "exported_at": datetime.utcnow().isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "preferred_currency": user.preferred_currency,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "categories": [
            {"id": c.id, "name": c.name, "created_at": c.created_at.isoformat()}
            for c in categories
        ],
        "expenses": [
            {
                "id": e.id,
                "category_id": e.category_id,
                "amount": float(e.amount),
                "currency": e.currency,
                "expense_type": e.expense_type,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat() if e.spent_at else None,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in expenses
        ],
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "currency": b.currency,
                "next_due_date": b.next_due_date.isoformat() if b.next_due_date else None,
                "cadence": b.cadence.value,
                "autopay_enabled": b.autopay_enabled,
                "active": b.active,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bills
        ],
        "reminders": [
            {
                "id": r.id,
                "bill_id": r.bill_id,
                "message": r.message,
                "send_at": r.send_at.isoformat() if r.send_at else None,
                "sent": r.sent,
                "channel": r.channel,
            }
            for r in reminders
        ],
    }


def create_backup(user_id: int, password: str, export_type: str = "full") -> dict:
    data = _collect_user_data(user_id)
    plaintext = json.dumps(data, indent=2)
    encrypted = _encrypt(plaintext, password)
    pw_hash, pw_salt = _password_hash(password)

    record_count = (
        len(data["expenses"]) + len(data["bills"])
        + len(data["reminders"]) + len(data["categories"])
    )
    payload_json = json.dumps(encrypted)
    size_bytes = len(payload_json.encode("utf-8"))

    expiry = datetime.utcnow() + timedelta(days=30)
    backup = BackupExport(
        user_id=user_id,
        filename=f"finmind-backup-{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.enc",
        encrypted_payload=payload_json,
        encryption_iv=encrypted["iv"],
        encryption_tag=encrypted["tag"],
        export_type=export_type,
        status="completed",
        record_count=record_count,
        size_bytes=size_bytes,
        password_hash=f"{pw_salt}${pw_hash}",
        expires_at=expiry,
    )
    db.session.add(backup)
    db.session.commit()

    logger.info("Backup created user=%s export=%s records=%d", user_id, export_type, record_count)
    return {
        "id": backup.id,
        "filename": backup.filename,
        "export_type": backup.export_type,
        "record_count": record_count,
        "size_bytes": size_bytes,
        "expires_at": expiry.isoformat(),
        "created_at": backup.created_at.isoformat() if backup.created_at else None,
        "algo": ENCRYPTION_ALGO,
        "kdf": KEY_DERIVATION,
    }


def list_backups(user_id: int, limit: int = 20) -> list[dict]:
    backups = (
        BackupExport.query
        .filter(
            BackupExport.user_id == user_id,
            BackupExport.status == "completed",
        )
        .order_by(BackupExport.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": b.id,
            "filename": b.filename,
            "export_type": b.export_type,
            "record_count": b.record_count,
            "size_bytes": b.size_bytes,
            "expires_at": b.expires_at.isoformat() if b.expires_at else None,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        }
        for b in backups
    ]


def get_backup(user_id: int, backup_id: int) -> dict | None:
    backup = BackupExport.query.filter_by(id=backup_id, user_id=user_id).first()
    if not backup:
        return None
    return {
        "id": backup.id,
        "filename": backup.filename,
        "export_type": backup.export_type,
        "record_count": backup.record_count,
        "size_bytes": backup.size_bytes,
        "password_hash": backup.password_hash,
        "encrypted_payload": backup.encrypted_payload,
        "expires_at": backup.expires_at.isoformat() if backup.expires_at else None,
        "created_at": backup.created_at.isoformat() if backup.created_at else None,
    }


def decrypt_backup(user_id: int, backup_id: int, password: str) -> dict | None:
    backup = BackupExport.query.filter_by(id=backup_id, user_id=user_id).first()
    if not backup:
        return None
    pw_salt, pw_hash = backup.password_hash.split("$", 1)
    if not _verify_password(password, pw_hash, pw_salt):
        return None
    encrypted = json.loads(backup.encrypted_payload)
    plaintext = _decrypt(encrypted, password)
    return json.loads(plaintext)


def delete_backup(user_id: int, backup_id: int) -> bool:
    backup = BackupExport.query.filter_by(id=backup_id, user_id=user_id).first()
    if not backup:
        return False
    db.session.delete(backup)
    db.session.commit()
    logger.info("Backup deleted user=%s backup=%d", user_id, backup_id)
    return True
