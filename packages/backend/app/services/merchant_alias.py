"""Smart payee & merchant alias management."""

from ..extensions import db
from ..models import Expense
from datetime import datetime
import logging

logger = logging.getLogger("finmind.merchant")


class MerchantAlias(db.Model):
    __tablename__ = "merchant_aliases"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    pattern = db.Column(db.String(200), nullable=False)  # raw merchant string
    display_name = db.Column(db.String(200), nullable=False)  # clean name
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


def resolve_merchant(user_id: int, raw_name: str) -> dict:
    """Resolve a raw merchant/payee string to a clean display name.

    Checks user's alias table first, then applies basic normalization.
    """
    if not raw_name:
        return {"display_name": raw_name, "matched_alias": False}

    # Check user aliases
    alias = (
        db.session.query(MerchantAlias)
        .filter(
            MerchantAlias.user_id == user_id,
            MerchantAlias.pattern == raw_name.lower().strip(),
        )
        .first()
    )

    if alias:
        return {
            "display_name": alias.display_name,
            "category_id": alias.category_id,
            "matched_alias": True,
        }

    # Basic normalization
    cleaned = _normalize_merchant_name(raw_name)
    return {"display_name": cleaned, "matched_alias": False}


def create_alias(user_id: int, pattern: str, display_name: str, category_id: int | None = None) -> dict:
    """Create a merchant alias mapping."""
    alias = MerchantAlias(
        user_id=user_id,
        pattern=pattern.lower().strip(),
        display_name=display_name,
        category_id=category_id,
    )
    db.session.add(alias)
    db.session.commit()
    return {"id": alias.id, "pattern": alias.pattern, "display_name": alias.display_name}


def get_aliases(user_id: int) -> list[dict]:
    """Get all merchant aliases for a user."""
    aliases = db.session.query(MerchantAlias).filter_by(user_id=user_id).all()
    return [
        {"id": a.id, "pattern": a.pattern, "display_name": a.display_name, "category_id": a.category_id}
        for a in aliases
    ]


def suggest_aliases(user_id: int) -> list[dict]:
    """Suggest merchant aliases based on frequent similar expense notes."""
    expenses = (
        db.session.query(Expense.notes)
        .filter(Expense.user_id == user_id, Expense.notes.isnot(None))
        .all()
    )

    # Count frequency of normalized names
    freq: dict[str, int] = {}
    for (notes,) in expenses:
        if notes:
            normalized = _normalize_merchant_name(notes)
            freq.setdefault(normalized, 0)
            freq[normalized] += 1

    # Suggest aliases for frequent merchants without existing alias
    existing = {a.pattern for a in db.session.query(MerchantAlias).filter_by(user_id=user_id).all()}
    suggestions = []
    for name, count in sorted(freq.items(), key=lambda x: -x[1])[:20]:
        if name.lower() not in existing and count >= 3:
            suggestions.append({"raw": name, "suggested_name": name.title(), "frequency": count})

    return suggestions


def _normalize_merchant_name(raw: str) -> str:
    """Basic merchant name normalization."""
    import re
    # Remove transaction IDs, dates, reference numbers
    cleaned = re.sub(r'\b\d{6,}\b', '', raw)
    cleaned = re.sub(r'\b[A-Z]{2,3}\d+\b', '', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # Title case
    return cleaned.title() if cleaned else raw
