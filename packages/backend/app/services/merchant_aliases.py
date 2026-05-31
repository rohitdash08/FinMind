import logging
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, MerchantAlias

logger = logging.getLogger("finmind.merchant_aliases")

SIMILARITY_THRESHOLD = 0.8


def create_alias(user_id: int, canonical_name: str, alias: str) -> dict[str, Any]:
    existing = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=user_id, alias=alias)
        .first()
    )
    if existing:
        if existing.canonical_name != canonical_name:
            return {"error": f"alias '{alias}' already mapped to '{existing.canonical_name}'"}
        return {"id": existing.id, "canonical_name": canonical_name, "alias": alias}
    ma = MerchantAlias(user_id=user_id, canonical_name=canonical_name, alias=alias)
    db.session.add(ma)
    db.session.commit()
    logger.info("Created alias user=%s canonical=%s alias=%s", user_id, canonical_name, alias)
    return {"id": ma.id, "canonical_name": canonical_name, "alias": alias}


def get_aliases(user_id: int) -> list[dict[str, Any]]:
    rows = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=user_id)
        .order_by(MerchantAlias.canonical_name)
        .all()
    )
    return [
        {"id": r.id, "canonical_name": r.canonical_name, "alias": r.alias} for r in rows
    ]


def get_canonical(user_id: int, raw_name: str) -> str:
    row = (
        db.session.query(MerchantAlias)
        .filter_by(user_id=user_id, alias=raw_name)
        .first()
    )
    if row:
        return row.canonical_name
    return raw_name


def update_alias(user_id: int, alias_id: int, canonical_name: str) -> dict[str, Any] | None:
    ma = db.session.get(MerchantAlias, alias_id)
    if not ma or ma.user_id != user_id:
        return None
    ma.canonical_name = canonical_name
    db.session.commit()
    logger.info("Updated alias id=%s canonical=%s", alias_id, canonical_name)
    return {"id": ma.id, "canonical_name": ma.canonical_name, "alias": ma.alias}


def delete_alias(user_id: int, alias_id: int) -> bool:
    ma = db.session.get(MerchantAlias, alias_id)
    if not ma or ma.user_id != user_id:
        return False
    db.session.delete(ma)
    db.session.commit()
    logger.info("Deleted alias id=%s", alias_id)
    return True


def suggest_aliases(user_id: int) -> list[dict[str, Any]]:
    descriptions = (
        db.session.query(Expense.notes)
        .filter(Expense.user_id == user_id, Expense.notes.isnot(None))
        .distinct()
        .all()
    )
    names = [r[0].strip() for r in descriptions if r[0] and r[0].strip()]
    existing_aliases = {
        ma.alias.lower()
        for ma in db.session.query(MerchantAlias).filter_by(user_id=user_id).all()
    }

    suggestions: list[dict[str, Any]] = []
    for i, name_a in enumerate(names):
        for name_b in names[i + 1 :]:
            if name_a.lower() == name_b.lower():
                continue
            if name_a.lower() in existing_aliases or name_b.lower() in existing_aliases:
                continue
            score = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
            if score >= SIMILARITY_THRESHOLD:
                suggestions.append(
                    {
                        "name_a": name_a,
                        "name_b": name_b,
                        "similarity": round(score, 4),
                        "suggested_canonical": name_a if len(name_a) <= len(name_b) else name_b,
                    }
                )
    suggestions.sort(key=lambda s: s["similarity"], reverse=True)
    return suggestions[:50]


def merge_aliases(user_id: int, source_id: int, target_id: int) -> dict[str, Any] | None:
    source = db.session.get(MerchantAlias, source_id)
    target = db.session.get(MerchantAlias, target_id)
    if not source or not target or source.user_id != user_id or target.user_id != user_id:
        return None
    source.canonical_name = target.canonical_name
    db.session.commit()
    return {"id": source.id, "canonical_name": source.canonical_name, "alias": source.alias}
