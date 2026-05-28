"""Client-Side Encryption Service for FinMind.

Provides:
- AES-256-GCM encryption/decryption for financial data
- Key derivation from user password (PBKDF2)
- Field-level encryption (encrypt specific fields)
- Encrypted data export/import
- Key rotation support

Note: Actual crypto operations happen client-side in the browser.
This module provides server-side key management and field metadata.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("finmind.encryption")


class EncryptionMetadata:
    """Track which fields are encrypted and their key versions."""

    SENSITIVE_FIELDS = [
        "amount", "merchant", "description", "category",
        "account_number", "routing_number", "balance",
    ]

    def __init__(self):
        self._encrypted_fields = set()

    def mark_encrypted(self, field: str):
        self._encrypted_fields.add(field)

    def mark_decrypted(self, field: str):
        self._encrypted_fields.discard(field)

    def is_encrypted(self, field: str) -> bool:
        return field in self._encrypted_fields

    def get_encrypted_fields(self) -> list[str]:
        return list(self._encrypted_fields)

    @classmethod
    def from_dict(cls, data: dict) -> "EncryptionMetadata":
        meta = cls()
        meta._encrypted_fields = set(data.get("encrypted_fields", []))
        return meta

    def to_dict(self) -> dict:
        return {"encrypted_fields": list(self._encrypted_fields)}


class KeyManager:
    """Manage encryption keys for client-side encryption.

    Keys are never stored server-side in plain text.
    Server stores only key metadata and version info.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self._key_versions = {}  # version -> metadata

    def create_key_version(self) -> dict:
        """Create a new key version metadata entry.

        The actual key is derived client-side from user password + salt.
        Server stores only the salt and version info.
        """
        version = len(self._key_versions) + 1
        salt = secrets.token_hex(16)

        metadata = {
            "version": version,
            "salt": salt,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "algorithm": "AES-256-GCM",
            "kdf": "PBKDF2-SHA256",
            "kdf_iterations": 100000,
            "status": "active",
        }

        self._key_versions[version] = metadata
        return metadata

    def get_active_key(self) -> Optional[dict]:
        """Get the currently active key metadata."""
        active = [v for v in self._key_versions.values() if v["status"] == "active"]
        return active[-1] if active else None

    def rotate_key(self) -> dict:
        """Rotate encryption key - deactivate old, create new."""
        # Deactivate all existing keys
        for v in self._key_versions.values():
            v["status"] = "deprecated"

        # Create new active key
        return self.create_key_version()

    def get_key_history(self) -> list[dict]:
        """Get history of all key versions."""
        return list(self._key_versions.values())


class FieldEncryptor:
    """Server-side field encryption metadata and validation.

    Actual encryption happens client-side. Server validates
    that encrypted fields have proper format.
    """

    ENCRYPTED_PREFIX = "enc:v1:"
    IV_LENGTH = 12  # GCM IV length

    @staticmethod
    def is_encrypted_value(value: str) -> bool:
        """Check if a value appears to be encrypted."""
        if not isinstance(value, str):
            return False
        return value.startswith(FieldEncryptor.ENCRYPTED_PREFIX)

    @staticmethod
    def validate_encrypted_field(value: str, field_name: str) -> dict:
        """Validate that an encrypted field has proper format.

        Client should send: enc:v1:<base64_iv>:<base64_ciphertext>:<base64_tag>
        """
        if not FieldEncryptor.is_encrypted_value(value):
            return {"valid": False, "error": f"Field {field_name} is not encrypted"}

        parts = value.split(":")
        if len(parts) != 5:
            return {"valid": False, "error": f"Invalid encrypted format for {field_name}"}

        try:
            iv = base64.b64decode(parts[2])
            ciphertext = base64.b64decode(parts[3])
            tag = base64.b64decode(parts[4])

            if len(iv) != FieldEncryptor.IV_LENGTH:
                return {"valid": False, "error": f"Invalid IV length for {field_name}"}

            return {"valid": True, "field": field_name}

        except Exception as e:
            return {"valid": False, "error": f"Invalid base64 in {field_name}: {str(e)}"}

    @staticmethod
    def validate_encrypted_record(record: dict, sensitive_fields: list[str] = None) -> dict:
        """Validate all sensitive fields in a record are properly encrypted."""
        fields = sensitive_fields or EncryptionMetadata.SENSITIVE_FIELDS
        results = []
        all_valid = True

        for field in fields:
            value = record.get(field)
            if value is None:
                continue  # Field not present, skip

            if isinstance(value, (int, float)):
                # Numeric values should be encrypted as strings client-side
                results.append({
                    "field": field,
                    "valid": False,
                    "error": f"Numeric value for {field} should be encrypted string",
                })
                all_valid = False
            elif isinstance(value, str):
                result = FieldEncryptor.validate_encrypted_field(value, field)
                results.append(result)
                if not result["valid"]:
                    all_valid = False

        return {"valid": all_valid, "field_results": results}


def generate_client_encryption_config(user_id: str) -> dict:
    """Generate client-side encryption configuration for a user."""
    km = KeyManager(user_id)
    key_meta = km.create_key_version()

    return {
        "user_id": user_id,
        "encryption": {
            "algorithm": "AES-256-GCM",
            "key_derivation": {
                "function": "PBKDF2",
                "hash": "SHA-256",
                "iterations": key_meta["kdf_iterations"],
                "salt": key_meta["salt"],
            },
            "sensitive_fields": EncryptionMetadata.SENSITIVE_FIELDS,
        },
        "key_version": key_meta["version"],
        "instructions": {
            "encrypt": "Use Web Crypto API: crypto.subtle.encrypt({name:'AES-GCM',iv}, key, data)",
            "decrypt": "Use Web Crypto API: crypto.subtle.decrypt({name:'AES-GCM',iv}, key, data)",
            "format": "enc:v1:<base64_iv>:<base64_ciphertext>:<base64_auth_tag>",
        },
    }
