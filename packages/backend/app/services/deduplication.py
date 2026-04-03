"""Transaction deduplication intelligence.

Finds potential duplicate expenses using fuzzy matching on:
- Exact duplicates (same amount + date + description)
- Near duplicates (same amount + date, similar description)
- Temporal duplicates (same amount + description within N days)

Confidence scoring: exact=100, near=80, temporal=60.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import TypedDict

from sqlalchemy import func

from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.deduplication")


class DuplicateGroup(TypedDict):
    confidence: int  # 0-100
    match_type: str  # exact | near | temporal
    expenses: list[dict]
    suggestion: str


def find_duplicates(
    user_id: int,
    lookback_days: int = 90,
    similarity_threshold: float = 0.7,
) -> list[DuplicateGroup]:
    """Find potential duplicate expenses."""
    cutoff = date.today() - timedelta(days=lookback_days)

    expenses = (
        db.session.query(Expense)
        .filter(Expense.user_id == user_id, Expense.spent_at >= cutoff)
        .order_by(Expense.spent_at.desc())
        .all()
    )

    if len(expenses) < 2:
        return []

    groups: list[DuplicateGroup] = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, e1 in enumerate(expenses):
        for e2 in expenses[i + 1:]:
            pair = (min(e1.id, e2.id), max(e1.id, e2.id))
            if pair in seen_pairs:
                continue

            match = _check_duplicate(e1, e2, similarity_threshold)
            if match:
                seen_pairs.add(pair)
                groups.append(match)

    # Sort by confidence desc
    groups.sort(key=lambda g: g["confidence"], reverse=True)

    logger.info("Dedup scan user=%s: %d potential duplicates", user_id, len(groups))
    return groups


def _check_duplicate(e1: Expense, e2: Expense, threshold: float) -> DuplicateGroup | None:
    """Check if two expenses are potential duplicates."""
    amt_match = float(e1.amount) == float(e2.amount)
    date_match = e1.spent_at == e2.spent_at
    desc1 = (e1.notes or "").lower().strip()
    desc2 = (e2.notes or "").lower().strip()
    desc_exact = desc1 == desc2
    desc_similar = SequenceMatcher(None, desc1, desc2).ratio() >= threshold if desc1 and desc2 else False
    date_close = abs((e1.spent_at - e2.spent_at).days) <= 3

    e1_dict = _to_dict(e1)
    e2_dict = _to_dict(e2)

    # Exact duplicate
    if amt_match and date_match and desc_exact:
        return DuplicateGroup(
            confidence=100,
            match_type="exact",
            expenses=[e1_dict, e2_dict],
            suggestion="These appear identical. Consider removing one.",
        )

    # Near duplicate (same amount+date, similar description)
    if amt_match and date_match and desc_similar:
        return DuplicateGroup(
            confidence=80,
            match_type="near",
            expenses=[e1_dict, e2_dict],
            suggestion="Same amount and date with similar descriptions. Likely duplicate.",
        )

    # Temporal duplicate (same amount+description, close dates)
    if amt_match and date_close and (desc_exact or desc_similar):
        return DuplicateGroup(
            confidence=60,
            match_type="temporal",
            expenses=[e1_dict, e2_dict],
            suggestion=f"Same transaction {abs((e1.spent_at - e2.spent_at).days)} days apart. May be duplicate entry.",
        )

    return None


def merge_duplicates(user_id: int, keep_id: int, remove_id: int) -> bool:
    """Remove one expense from a duplicate pair (keep the other)."""
    keep = db.session.get(Expense, keep_id)
    remove = db.session.get(Expense, remove_id)

    if not keep or not remove:
        return False
    if keep.user_id != user_id or remove.user_id != user_id:
        return False

    db.session.delete(remove)
    db.session.commit()
    logger.info("Merged duplicate: kept=%s removed=%s user=%s", keep_id, remove_id, user_id)
    return True


def _to_dict(e: Expense) -> dict:
    return {
        "id": e.id,
        "amount": float(e.amount),
        "currency": e.currency,
        "description": e.notes or "",
        "date": e.spent_at.isoformat(),
        "category_id": e.category_id,
    }
