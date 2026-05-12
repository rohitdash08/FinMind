"""Transaction deduplication intelligence."""

from datetime import timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.dedup")


def find_duplicates(user_id: int, window_hours: int = 24) -> list[dict]:
    """Find potential duplicate transactions.

    Detects expenses with same amount, similar notes, within time window.
    """
    expenses = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .order_by(Expense.spent_at.desc(), Expense.created_at.desc())
        .limit(500)
        .all()
    )

    duplicates = []
    seen = set()

    for i, exp in enumerate(expenses):
        if exp.id in seen:
            continue
        group = [exp]

        for j in range(i + 1, len(expenses)):
            other = expenses[j]
            if other.id in seen:
                continue
            if _is_potential_duplicate(exp, other, window_hours):
                group.append(other)
                seen.add(other.id)

        if len(group) > 1:
            seen.add(exp.id)
            duplicates.append({
                "amount": float(exp.amount),
                "notes": exp.notes,
                "date": exp.spent_at.isoformat() if exp.spent_at else None,
                "count": len(group),
                "expense_ids": [e.id for e in group],
                "confidence": _calculate_confidence(group),
            })

    return sorted(duplicates, key=lambda d: -d["confidence"])


def _is_potential_duplicate(a: Expense, b: Expense, window_hours: int) -> bool:
    """Check if two expenses are potential duplicates."""
    # Same amount
    if Decimal(str(a.amount)) != Decimal(str(b.amount)):
        return False

    # Within time window
    if a.spent_at and b.spent_at:
        diff = abs((a.spent_at - b.spent_at).days)
        if diff > window_hours // 24 + 1:
            return False

    # Similar notes
    if a.notes and b.notes:
        if a.notes.lower().strip() == b.notes.lower().strip():
            return True
        # Fuzzy: first 10 chars match
        if a.notes[:10].lower() == b.notes[:10].lower():
            return True

    # Same amount + same day + no notes = likely duplicate
    if not a.notes and not b.notes and a.spent_at == b.spent_at:
        return True

    return False


def _calculate_confidence(group: list[Expense]) -> float:
    """Calculate confidence that a group contains duplicates (0-1)."""
    if len(group) < 2:
        return 0.0

    score = 0.5  # Base: same amount

    # Same notes boost
    notes = [e.notes for e in group if e.notes]
    if len(set(n.lower().strip() for n in notes)) == 1:
        score += 0.3

    # Same day boost
    dates = [e.spent_at for e in group if e.spent_at]
    if len(set(dates)) == 1:
        score += 0.2

    return min(score, 1.0)
