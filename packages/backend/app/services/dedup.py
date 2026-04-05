"""Transaction deduplication intelligence (issue #113)."""
import hashlib, logging
from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.dedup")
DEDUP_WINDOW_DAYS = 3


def _fingerprint(amount: float, spent_at: date, notes: str = "") -> str:
    raw = f"{round(amount,2)}|{spent_at.isoformat()}|{(notes or '').strip().lower()[:50]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_duplicate(user_id: int, amount: float, spent_at: date,
                 notes: str = "", window_days: int = DEDUP_WINDOW_DAYS) -> dict:
    """Check if a transaction looks like a duplicate of an existing one."""
    window_start = spent_at - timedelta(days=window_days)
    candidates = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= window_start,
            Expense.spent_at <= spent_at + timedelta(days=window_days),
            Expense.amount == Decimal(str(round(amount, 2))),
        ).all()
    )

    for c in candidates:
        if c.spent_at == spent_at:
            return {"duplicate": True, "confidence": "high",
                    "match_id": c.id, "reason": "same amount + same date"}
        days_diff = abs((c.spent_at - spent_at).days)
        if days_diff <= 1:
            return {"duplicate": True, "confidence": "medium",
                    "match_id": c.id, "reason": f"same amount, {days_diff}d apart"}
        if days_diff <= window_days:
            return {"duplicate": True, "confidence": "low",
                    "match_id": c.id, "reason": f"same amount within {days_diff} days"}

    return {"duplicate": False, "confidence": None, "match_id": None, "reason": None}


def find_all_duplicates(user_id: int) -> list:
    """Scan all expenses and return suspected duplicate pairs."""
    expenses = (db.session.query(Expense)
                .filter_by(user_id=user_id)
                .order_by(Expense.spent_at, Expense.amount).all())
    pairs, seen = [], set()
    for i, a in enumerate(expenses):
        for b in expenses[i+1:]:
            if abs((b.spent_at - a.spent_at).days) > DEDUP_WINDOW_DAYS: break
            if a.amount == b.amount and (a.id, b.id) not in seen:
                seen.add((a.id, b.id))
                pairs.append({"expense_a": a.id, "expense_b": b.id,
                               "amount": float(a.amount),
                               "date_a": a.spent_at.isoformat(),
                               "date_b": b.spent_at.isoformat(),
                               "days_apart": abs((b.spent_at - a.spent_at).days)})
    return pairs
