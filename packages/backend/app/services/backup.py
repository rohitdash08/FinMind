"""
Secure backup & encrypted export options (issue #126).
AES-256-GCM encryption via cryptography library.
"""
import io, json, logging, os, zipfile
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
import base64, secrets
from ..extensions import db
from ..models import Expense, Category, Bill, User

logger = logging.getLogger("finmind.backup")


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return kdf.derive(password.encode())


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _collect_user_data(user_id: int) -> dict:
    user = db.session.get(User, user_id)
    expenses = db.session.query(Expense).filter_by(user_id=user_id).all()
    categories = db.session.query(Category).filter_by(user_id=user_id).all()
    bills = db.session.query(Bill).filter_by(user_id=user_id).all()
    return {
        "version": 1, "exported_at": _utcnow(), "user_id": user_id,
        "email": user.email if user else None,
        "expenses": [{"id": e.id, "amount": float(e.amount), "currency": e.currency,
                      "type": e.expense_type, "notes": e.notes,
                      "spent_at": e.spent_at.isoformat()} for e in expenses],
        "categories": [{"id": c.id, "name": c.name} for c in categories],
        "bills": [{"id": b.id, "name": b.name, "amount": float(b.amount)} for b in bills],
    }


def create_encrypted_backup(user_id: int, password: str) -> bytes:
    """
    Creates AES-256-GCM encrypted backup ZIP.
    Returns raw bytes: [4-byte salt_len][salt][nonce][ciphertext]
    """
    data = json.dumps(_collect_user_data(user_id)).encode()
    salt = secrets.token_bytes(16)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    # Format: salt(16) + nonce(12) + ciphertext
    payload = salt + nonce + ciphertext
    logger.info("Encrypted backup created for user %d (%d bytes)", user_id, len(payload))
    return payload


def decrypt_backup(payload: bytes, password: str) -> dict:
    """Decrypt a backup payload and return the data dict."""
    salt = payload[:16]
    nonce = payload[16:28]
    ciphertext = payload[28:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return json.loads(plaintext)


def create_plaintext_backup(user_id: int) -> bytes:
    """Unencrypted ZIP backup (for users who prefer it)."""
    data = _collect_user_data(user_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup.json", json.dumps(data, indent=2))
    return buf.getvalue()
