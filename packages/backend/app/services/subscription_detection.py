"""Subscription cost increase detection service."""

from datetime import datetime, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Bill
import logging

logger = logging.getLogger("finmind.subscriptions")


def detect_cost_increases(user_id: int, threshold_pct: float = 5.0) -> list[dict]:
    """Detect bills whose amount has increased compared to historical average.

    Args:
        user_id: User to check.
        threshold_pct: Minimum percentage increase to flag (default 5%).

    Returns:
        List of detected increases with bill info and change details.
    """
    active_bills = (
        db.session.query(Bill)
        .filter_by(user_id=user_id, active=True)
        .all()
    )

    increases = []
    for bill in active_bills:
        # Find previous bills with same name (historical records)
        history = (
            db.session.query(Bill)
            .filter(
                Bill.user_id == user_id,
                Bill.name == bill.name,
                Bill.id != bill.id,
            )
            .order_by(Bill.created_at.desc())
            .limit(5)
            .all()
        )

        if not history:
            continue

        avg_amount = sum(Decimal(str(h.amount)) for h in history) / len(history)
        current = Decimal(str(bill.amount))

        if avg_amount > 0:
            change_pct = float((current - avg_amount) / avg_amount * 100)
            if change_pct >= threshold_pct:
                increases.append({
                    "bill_id": bill.id,
                    "name": bill.name,
                    "current_amount": float(current),
                    "previous_average": float(avg_amount),
                    "increase_percent": round(change_pct, 1),
                    "currency": bill.currency,
                })

    return increases
