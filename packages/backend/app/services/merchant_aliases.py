"""
Smart payee & merchant alias management service (#114).

Allows users to create canonical merchant names and map raw payee strings
to them. When a canonical name is set, expense lookups and reports use it
instead of the raw transaction description.
"""

from __future__ import annotations

from typing import Any

from ..extensions import db
from ..models import MerchantAlias


def get_aliases_for_user(uid: int) -> list[dict]:
    """Return all merchant aliases for a user."""
    aliases = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=uid)
        .order_by(MerchantAlias.canonical_name)
        .all()
    )
    return [
        {
            "id": a.id,
            "raw_name": a.raw_name,
            "canonical_name": a.canonical_name,
        }
        for a in aliases
    ]


def create_alias(uid: int, raw_name: str, canonical_name: str) -> dict:
    """Create or update a merchant alias."""
    raw_name = raw_name.strip()
    canonical_name = canonical_name.strip()

    if not raw_name or not canonical_name:
        raise ValueError("raw_name and canonical_name must not be empty")

    # Upsert: update if raw_name already exists for this user
    existing = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=uid, raw_name=raw_name)
        .first()
    )
    if existing:
        existing.canonical_name = canonical_name
        db.session.commit()
        return {"id": existing.id, "raw_name": existing.raw_name, "canonical_name": existing.canonical_name}

    alias = MerchantAlias(user_id=uid, raw_name=raw_name, canonical_name=canonical_name)
    db.session.add(alias)
    db.session.commit()
    return {"id": alias.id, "raw_name": alias.raw_name, "canonical_name": alias.canonical_name}


def delete_alias(uid: int, alias_id: int) -> bool:
    """Delete a merchant alias. Returns True if deleted, False if not found."""
    alias = (
        db.session.query(MerchantAlias)
        .filter_by(id=alias_id, user_id=uid)
        .first()
    )
    if not alias:
        return False
    db.session.delete(alias)
    db.session.commit()
    return True


def resolve_merchant(uid: int, raw_name: str) -> str:
    """Return the canonical name for a raw payee string, or raw_name if none exists."""
    alias = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=uid, raw_name=raw_name.strip())
        .first()
    )
    return alias.canonical_name if alias else raw_name
