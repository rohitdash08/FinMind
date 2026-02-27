"""Smart payee & merchant alias management.

Maps messy transaction descriptions to clean merchant names,
supports user-defined aliases, and auto-suggests merges for similar names.
"""

from datetime import datetime
from difflib import SequenceMatcher
from collections import defaultdict
from sqlalchemy import func
from ..extensions import db
from ..models import Expense


class MerchantAlias(db.Model):
    __tablename__ = "merchant_aliases"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    raw_name = db.Column(db.String(300), nullable=False)
    display_name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("user_id", "raw_name"),)


def set_alias(user_id: int, raw_name: str, display_name: str) -> dict:
    """Create or update a merchant alias."""
    raw_name = raw_name.strip()
    display_name = display_name.strip()
    if not raw_name or not display_name:
        raise ValueError("raw_name and display_name are required")

    existing = MerchantAlias.query.filter_by(user_id=user_id, raw_name=raw_name).first()
    if existing:
        existing.display_name = display_name
    else:
        existing = MerchantAlias(user_id=user_id, raw_name=raw_name, display_name=display_name)
        db.session.add(existing)
    db.session.commit()
    return _serialize(existing)


def get_aliases(user_id: int) -> list[dict]:
    aliases = MerchantAlias.query.filter_by(user_id=user_id).order_by(MerchantAlias.display_name).all()
    return [_serialize(a) for a in aliases]


def delete_alias(user_id: int, alias_id: int) -> bool:
    a = MerchantAlias.query.filter_by(id=alias_id, user_id=user_id).first()
    if not a:
        return False
    db.session.delete(a)
    db.session.commit()
    return True


def resolve_name(user_id: int, raw_name: str) -> str:
    """Resolve a raw transaction description to a display name."""
    alias = MerchantAlias.query.filter_by(user_id=user_id, raw_name=raw_name).first()
    return alias.display_name if alias else raw_name


def suggest_merges(user_id: int, threshold: float = 0.7) -> list[dict]:
    """Find similar merchant descriptions that could be merged."""
    descriptions = (
        db.session.query(Expense.description, func.count(Expense.id))
        .filter(Expense.user_id == user_id)
        .group_by(Expense.description)
        .having(func.count(Expense.id) >= 1)
        .all()
    )

    names = [(d, c) for d, c in descriptions if d]
    suggestions = []
    seen = set()

    for i, (name_a, count_a) in enumerate(names):
        for j, (name_b, count_b) in enumerate(names):
            if i >= j:
                continue
            pair_key = tuple(sorted([name_a, name_b]))
            if pair_key in seen:
                continue

            similarity = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
            if similarity >= threshold:
                seen.add(pair_key)
                suggested = name_a if count_a >= count_b else name_b
                suggestions.append({
                    "names": [name_a, name_b],
                    "counts": [count_a, count_b],
                    "similarity": round(similarity, 2),
                    "suggested_name": suggested,
                })

    suggestions.sort(key=lambda x: x["similarity"], reverse=True)
    return suggestions


def bulk_set_aliases(user_id: int, aliases: list[dict]) -> list[dict]:
    """Set multiple aliases at once. Each dict needs raw_name and display_name."""
    results = []
    for a in aliases:
        results.append(set_alias(user_id, a["raw_name"], a["display_name"]))
    return results


def merchant_summary(user_id: int) -> dict:
    """Summary of merchant/payee usage with alias resolution."""
    rows = (
        db.session.query(Expense.description, func.count(Expense.id), func.sum(Expense.amount))
        .filter(Expense.user_id == user_id)
        .group_by(Expense.description)
        .all()
    )

    alias_map = {a.raw_name: a.display_name for a in MerchantAlias.query.filter_by(user_id=user_id).all()}

    merged = defaultdict(lambda: {"count": 0, "total": 0, "raw_names": []})
    for desc, count, total in rows:
        display = alias_map.get(desc, desc)
        merged[display]["count"] += count
        merged[display]["total"] += float(total)
        if desc not in merged[display]["raw_names"]:
            merged[display]["raw_names"].append(desc)

    merchants = [
        {"name": name, "transaction_count": d["count"], "total_spent": round(d["total"], 2), "raw_names": d["raw_names"]}
        for name, d in merged.items()
    ]
    merchants.sort(key=lambda x: x["total_spent"], reverse=True)

    return {
        "total_merchants": len(merchants),
        "total_aliases": len(alias_map),
        "merchants": merchants,
    }


def _serialize(a: MerchantAlias) -> dict:
    return {
        "id": a.id,
        "raw_name": a.raw_name,
        "display_name": a.display_name,
        "created_at": a.created_at.isoformat(),
    }
