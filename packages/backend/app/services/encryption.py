"""Client-side encryption for sensitive financial data.

Provides encryption/decryption utilities, key management,
and encrypted field storage for sensitive data like notes,
account numbers, and personal identifiers.
"""

import base64
import hashlib
import os
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from ..extensions import db


class EncryptionKey(db.Model):
    __tablename__ = "encryption_keys"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    salt = db.Column(db.String(64), nullable=False)
    key_hash = db.Column(db.String(128), nullable=False)  # verify passphrase
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    rotated_at = db.Column(db.DateTime, nullable=True)


class EncryptedField(db.Model):
    __tablename__ = "encrypted_fields"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    field_name = db.Column(db.String(100), nullable=False)
    encrypted_value = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "field_name"),)


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=480000)
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))


def _hash_key(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()


def setup_encryption(user_id: int, passphrase: str) -> dict:
    existing = EncryptionKey.query.filter_by(user_id=user_id).first()
    if existing:
        raise ValueError("Encryption already set up. Use rotate_key to change.")

    salt = os.urandom(16)
    key = _derive_key(passphrase, salt)

    record = EncryptionKey(
        user_id=user_id,
        salt=base64.b64encode(salt).decode(),
        key_hash=_hash_key(key),
    )
    db.session.add(record)
    db.session.commit()
    return {"status": "ok", "message": "Encryption configured"}


def verify_passphrase(user_id: int, passphrase: str) -> bool:
    record = EncryptionKey.query.filter_by(user_id=user_id).first()
    if not record:
        return False
    salt = base64.b64decode(record.salt)
    key = _derive_key(passphrase, salt)
    return _hash_key(key) == record.key_hash


def encrypt_field(user_id: int, passphrase: str, field_name: str, value: str) -> dict:
    record = EncryptionKey.query.filter_by(user_id=user_id).first()
    if not record:
        raise ValueError("Encryption not set up")

    salt = base64.b64decode(record.salt)
    key = _derive_key(passphrase, salt)
    if _hash_key(key) != record.key_hash:
        raise ValueError("Invalid passphrase")

    f = Fernet(key)
    encrypted = f.encrypt(value.encode()).decode()

    field = EncryptedField.query.filter_by(user_id=user_id, field_name=field_name).first()
    if field:
        field.encrypted_value = encrypted
    else:
        field = EncryptedField(user_id=user_id, field_name=field_name, encrypted_value=encrypted)
        db.session.add(field)
    db.session.commit()

    return {"field_name": field_name, "status": "encrypted"}


def decrypt_field(user_id: int, passphrase: str, field_name: str) -> str:
    record = EncryptionKey.query.filter_by(user_id=user_id).first()
    if not record:
        raise ValueError("Encryption not set up")

    salt = base64.b64decode(record.salt)
    key = _derive_key(passphrase, salt)
    if _hash_key(key) != record.key_hash:
        raise ValueError("Invalid passphrase")

    field = EncryptedField.query.filter_by(user_id=user_id, field_name=field_name).first()
    if not field:
        raise ValueError(f"Field not found: {field_name}")

    f = Fernet(key)
    return f.decrypt(field.encrypted_value.encode()).decode()


def list_fields(user_id: int) -> list[dict]:
    fields = EncryptedField.query.filter_by(user_id=user_id).all()
    return [{"field_name": f.field_name, "updated_at": f.updated_at.isoformat()} for f in fields]


def delete_field(user_id: int, field_name: str) -> bool:
    field = EncryptedField.query.filter_by(user_id=user_id, field_name=field_name).first()
    if not field:
        return False
    db.session.delete(field)
    db.session.commit()
    return True


def rotate_key(user_id: int, old_passphrase: str, new_passphrase: str) -> dict:
    record = EncryptionKey.query.filter_by(user_id=user_id).first()
    if not record:
        raise ValueError("Encryption not set up")

    old_salt = base64.b64decode(record.salt)
    old_key = _derive_key(old_passphrase, old_salt)
    if _hash_key(old_key) != record.key_hash:
        raise ValueError("Invalid old passphrase")

    # Decrypt all fields with old key, re-encrypt with new
    new_salt = os.urandom(16)
    new_key = _derive_key(new_passphrase, new_salt)
    old_fernet = Fernet(old_key)
    new_fernet = Fernet(new_key)

    fields = EncryptedField.query.filter_by(user_id=user_id).all()
    for field in fields:
        plaintext = old_fernet.decrypt(field.encrypted_value.encode())
        field.encrypted_value = new_fernet.encrypt(plaintext).decode()

    record.salt = base64.b64encode(new_salt).decode()
    record.key_hash = _hash_key(new_key)
    record.rotated_at = datetime.utcnow()
    db.session.commit()

    return {"status": "ok", "fields_rotated": len(fields)}


def has_encryption(user_id: int) -> bool:
    return EncryptionKey.query.filter_by(user_id=user_id).first() is not None
