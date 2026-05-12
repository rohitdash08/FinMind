"""Auto-detect subscriptions from recurring charges."""

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.subscriptions")


def detect_subscriptions(user_id: int, min_occurrences: int = 2) -> list[dict]:
    """Detect potential subscriptions from recurring expense patterns.

    Looks for expenses with similar amounts and regular intervals
    (weekly, monthly, yearly).
    """
    # Get last 90 days of expenses
    cutoff = date.today() - timedelta(days=90)
    expenses = (
        db.session.query(Expense)
        .filter(Expense.user_id == user_id, Expense.spent_at >= cutoff)
        .order_by(Expense.spent_at)
        .all()
    )

    # Group by similar amount + notes (potential subscription identifier)
    groups: dict[str, list] = defaultdict(list)
    for e in expenses:
        # Key: rounded amount + first 20 chars of notes
        key = f"{float(e.amount):.2f}|{(e.notes or '')[:20].lower().strip()}"
        groups[key].append(e)

    subscriptions = []
    for key, group in groups.items():
        if len(group) < min_occurrences:
            continue

        # Check if intervals are regular
        dates = sorted([e.spent_at for e in group])
        if len(dates) < 2:
            continue

        intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        avg_interval = sum(intervals) / len(intervals)

        # Detect cadence
        cadence = None
        if 5 <= avg_interval <= 9:
            cadence = "weekly"
        elif 25 <= avg_interval <= 35:
            cadence = "monthly"
        elif 350 <= avg_interval <= 380:
            cadence = "yearly"

        if cadence:
            amount = float(group[-1].amount)
            subscriptions.append({
                "name": group[-1].notes or f"Recurring {amount}",
                "amount": amount,
                "currency": group[-1].currency,
                "cadence": cadence,
                "occurrences": len(group),
                "last_charged": dates[-1].isoformat(),
                "avg_interval_days": round(avg_interval, 1),
            })

    return sorted(subscriptions, key=lambda s: -s["amount"])
