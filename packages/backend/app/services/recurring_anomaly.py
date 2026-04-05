"""Recurring transaction anomaly alerts (issue #108)."""
import logging
from sqlalchemy import func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.recurring_anomaly")


def detect_anomalies(user_id: int, std_multiplier: float = 2.0) -> list:
    """
    For each recurring charge group, flag transactions where amount
    deviates > N standard deviations from the group mean.
    """
    import re
    from math import sqrt
    expenses = (db.session.query(Expense)
                .filter(Expense.user_id == user_id, Expense.expense_type != "INCOME")
                .order_by(Expense.notes, Expense.spent_at).all())

    groups: dict = {}
    for e in expenses:
        key = re.sub(r'\d+', '', (e.notes or "Unknown").lower().strip())[:40]
        groups.setdefault(key, []).append(e)

    anomalies = []
    for desc, txns in groups.items():
        if len(txns) < 4: continue  # need enough history
        amounts = [float(t.amount) for t in txns]
        mean = sum(amounts) / len(amounts)
        variance = sum((x - mean)**2 for x in amounts) / len(amounts)
        std = sqrt(variance)
        if std < 0.01: continue  # all identical — normal

        for t in txns:
            amt = float(t.amount)
            if abs(amt - mean) > std_multiplier * std:
                anomalies.append({
                    "expense_id": t.id,
                    "description": t.notes or desc,
                    "amount": amt,
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                    "deviation": round(abs(amt - mean) / std, 2),
                    "date": t.spent_at.isoformat(),
                    "message": f"'{t.notes or desc}' charged ${amt:.2f} vs usual ${mean:.2f} (±{std:.2f})",
                })

    return sorted(anomalies, key=lambda x: -x["deviation"])
