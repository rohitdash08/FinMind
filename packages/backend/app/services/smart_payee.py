"""Smart payee & merchant alias management service.

Provides merchant CRUD, alias management, merging, and smart matching
so users can normalize and manage their payees/merchants.
"""

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import func

from app.extensions import db
from app.models import Merchant, MerchantAlias, Expense


def _normalize(name: str) -> str:
    """Normalize a merchant name for matching.

    Lowercases, strips whitespace, removes special chars, collapses spaces.
    """
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ── CRUD ───────────────────────────────────────────────────────────


def create_merchant(
    user_id: int,
    name: str,
    category_id: Optional[int] = None,
    default_currency: str = "INR",
    notes: Optional[str] = None,
) -> dict:
    """Create a new merchant."""
    normalized = _normalize(name)
    if not normalized:
        raise ValueError("Merchant name cannot be empty")

    existing = Merchant.query.filter_by(user_id=user_id, normalized_name=normalized).first()
    if existing:
        raise ValueError(f"Merchant '{name}' already exists")

    merchant = Merchant(
        user_id=user_id,
        name=name.strip(),
        normalized_name=normalized,
        category_id=category_id,
        default_currency=default_currency,
        notes=notes,
    )
    db.session.add(merchant)
    db.session.commit()
    return _serialize_merchant(merchant)


def get_merchant(user_id: int, merchant_id: int) -> Optional[dict]:
    """Get a single merchant by ID."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        return None
    return _serialize_merchant(merchant)


def list_merchants(
    user_id: int,
    search: Optional[str] = None,
    category_id: Optional[int] = None,
    sort_by: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List merchants with optional search and filtering."""
    query = Merchant.query.filter_by(user_id=user_id)

    if search:
        normalized_search = _normalize(search)
        query = query.filter(Merchant.normalized_name.contains(normalized_search))

    if category_id:
        query = query.filter_by(category_id=category_id)

    total = query.count()

    if sort_by == "transactions":
        query = query.order_by(Merchant.transaction_count.desc())
    elif sort_by == "spent":
        query = query.order_by(Merchant.total_spent.desc())
    elif sort_by == "recent":
        query = query.order_by(Merchant.last_transaction_date.desc().nullslast())
    else:
        query = query.order_by(Merchant.name.asc())

    merchants = query.offset(offset).limit(limit).all()

    return {
        "merchants": [_serialize_merchant(m) for m in merchants],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def update_merchant(user_id: int, merchant_id: int, **kwargs) -> Optional[dict]:
    """Update merchant fields."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        return None

    if "name" in kwargs:
        merchant.name = kwargs["name"].strip()
        merchant.normalized_name = _normalize(kwargs["name"])
    if "category_id" in kwargs:
        merchant.category_id = kwargs["category_id"]
    if "default_currency" in kwargs:
        merchant.default_currency = kwargs["default_currency"]
    if "notes" in kwargs:
        merchant.notes = kwargs["notes"]

    merchant.updated_at = datetime.utcnow()
    db.session.commit()
    return _serialize_merchant(merchant)


def delete_merchant(user_id: int, merchant_id: int) -> bool:
    """Delete a merchant and its aliases."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        return False
    db.session.delete(merchant)
    db.session.commit()
    return True


# ── Alias Management ──────────────────────────────────────────────


def add_alias(user_id: int, merchant_id: int, alias: str) -> dict:
    """Add an alias to a merchant."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        raise ValueError("Merchant not found")

    normalized = _normalize(alias)
    if not normalized:
        raise ValueError("Alias cannot be empty")

    # Check if alias already exists for this merchant
    existing = MerchantAlias.query.filter_by(
        merchant_id=merchant_id, normalized_alias=normalized
    ).first()
    if existing:
        raise ValueError(f"Alias '{alias}' already exists for this merchant")

    # Check if alias matches another merchant's name or alias
    conflict = Merchant.query.filter_by(user_id=user_id, normalized_name=normalized).first()
    if conflict and conflict.id != merchant_id:
        raise ValueError(f"Alias '{alias}' conflicts with merchant '{conflict.name}'")

    alias_obj = MerchantAlias(
        merchant_id=merchant_id,
        alias=alias.strip(),
        normalized_alias=normalized,
    )
    db.session.add(alias_obj)
    db.session.commit()
    return _serialize_alias(alias_obj)


def remove_alias(user_id: int, merchant_id: int, alias_id: int) -> bool:
    """Remove an alias from a merchant."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        return False

    alias_obj = MerchantAlias.query.filter_by(id=alias_id, merchant_id=merchant_id).first()
    if not alias_obj:
        return False

    db.session.delete(alias_obj)
    db.session.commit()
    return True


def list_aliases(user_id: int, merchant_id: int) -> list:
    """List all aliases for a merchant."""
    merchant = Merchant.query.filter_by(id=merchant_id, user_id=user_id).first()
    if not merchant:
        return []
    return [_serialize_alias(a) for a in merchant.aliases]


# ── Merge ─────────────────────────────────────────────────────────


def merge_merchants(user_id: int, target_id: int, source_ids: list[int]) -> dict:
    """Merge source merchants into target merchant.

    - Moves all aliases from sources to target
    - Adds source names as aliases of target
    - Aggregates transaction stats
    - Deletes source merchants
    """
    target = Merchant.query.filter_by(id=target_id, user_id=user_id).first()
    if not target:
        raise ValueError("Target merchant not found")

    merged_count = 0
    aliases_added = 0

    for source_id in source_ids:
        if source_id == target_id:
            continue

        source = Merchant.query.filter_by(id=source_id, user_id=user_id).first()
        if not source:
            continue

        # Move existing aliases to target
        for alias in source.aliases:
            # Check if alias already exists on target
            existing = MerchantAlias.query.filter_by(
                merchant_id=target_id, normalized_alias=alias.normalized_alias
            ).first()
            if not existing:
                alias.merchant_id = target_id
                aliases_added += 1
            else:
                db.session.delete(alias)

        # Add source name as alias of target
        normalized_source = _normalize(source.name)
        existing_alias = MerchantAlias.query.filter_by(
            merchant_id=target_id, normalized_alias=normalized_source
        ).first()
        if not existing_alias and normalized_source != target.normalized_name:
            new_alias = MerchantAlias(
                merchant_id=target_id,
                alias=source.name,
                normalized_alias=normalized_source,
            )
            db.session.add(new_alias)
            aliases_added += 1

        # Aggregate stats
        target.transaction_count += source.transaction_count
        target.total_spent += source.total_spent
        if source.last_transaction_date:
            if not target.last_transaction_date or source.last_transaction_date > target.last_transaction_date:
                target.last_transaction_date = source.last_transaction_date

        db.session.delete(source)
        merged_count += 1

    target.updated_at = datetime.utcnow()
    db.session.commit()

    return {
        "target": _serialize_merchant(target),
        "merged_count": merged_count,
        "aliases_added": aliases_added,
    }


# ── Smart Matching ────────────────────────────────────────────────


def match_merchant(user_id: int, name: str) -> Optional[dict]:
    """Find a merchant by name or alias (fuzzy matching).

    Checks exact match on merchant name, then aliases, then partial match.
    """
    normalized = _normalize(name)
    if not normalized:
        return None

    # Exact match on merchant name
    merchant = Merchant.query.filter_by(user_id=user_id, normalized_name=normalized).first()
    if merchant:
        return _serialize_merchant(merchant)

    # Exact match on alias
    alias = (
        MerchantAlias.query.join(Merchant)
        .filter(Merchant.user_id == user_id, MerchantAlias.normalized_alias == normalized)
        .first()
    )
    if alias:
        return _serialize_merchant(alias.merchant)

    # Partial match on merchant name
    merchant = (
        Merchant.query.filter_by(user_id=user_id)
        .filter(Merchant.normalized_name.contains(normalized))
        .first()
    )
    if merchant:
        return _serialize_merchant(merchant)

    return None


def suggest_duplicates(user_id: int) -> list:
    """Find potential duplicate merchants based on name similarity."""
    merchants = Merchant.query.filter_by(user_id=user_id).order_by(Merchant.normalized_name).all()
    duplicates = []
    seen = set()

    for i, m1 in enumerate(merchants):
        for m2 in merchants[i + 1:]:
            pair_key = (min(m1.id, m2.id), max(m1.id, m2.id))
            if pair_key in seen:
                continue

            # Check if one name contains the other
            if m1.normalized_name in m2.normalized_name or m2.normalized_name in m1.normalized_name:
                duplicates.append({
                    "merchant_a": _serialize_merchant(m1),
                    "merchant_b": _serialize_merchant(m2),
                    "similarity": "substring_match",
                })
                seen.add(pair_key)
                continue

            # Check word overlap
            words1 = set(m1.normalized_name.split())
            words2 = set(m2.normalized_name.split())
            if words1 and words2:
                overlap = len(words1 & words2) / max(len(words1), len(words2))
                if overlap >= 0.5:
                    duplicates.append({
                        "merchant_a": _serialize_merchant(m1),
                        "merchant_b": _serialize_merchant(m2),
                        "similarity": f"word_overlap_{overlap:.0%}",
                    })
                    seen.add(pair_key)

    return duplicates


# ── Helpers ───────────────────────────────────────────────────────


def _serialize_merchant(merchant: Merchant) -> dict:
    return {
        "id": merchant.id,
        "user_id": merchant.user_id,
        "name": merchant.name,
        "normalized_name": merchant.normalized_name,
        "category_id": merchant.category_id,
        "default_currency": merchant.default_currency,
        "notes": merchant.notes,
        "transaction_count": merchant.transaction_count,
        "total_spent": float(merchant.total_spent or 0),
        "last_transaction_date": str(merchant.last_transaction_date) if merchant.last_transaction_date else None,
        "aliases": [_serialize_alias(a) for a in merchant.aliases],
        "created_at": merchant.created_at.isoformat() if merchant.created_at else None,
        "updated_at": merchant.updated_at.isoformat() if merchant.updated_at else None,
    }


def _serialize_alias(alias: MerchantAlias) -> dict:
    return {
        "id": alias.id,
        "merchant_id": alias.merchant_id,
        "alias": alias.alias,
        "normalized_alias": alias.normalized_alias,
        "created_at": alias.created_at.isoformat() if alias.created_at else None,
    }
