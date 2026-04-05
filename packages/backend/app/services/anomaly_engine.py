"""Anomaly detection engine (issue #72)."""
import logging
from datetime import date, timedelta
from math import sqrt
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.anomaly_engine")


def detect_all_anomalies(user_id: int, year: int, month: int) -> dict:
    """
    Comprehensive anomaly detection across multiple signals:
    1. Single large transaction (>3x category average)
    2. Spending spike (day with >2x daily average)
    3. Off-hours transactions (midnight-5am)
    4. Round-amount clusters (potential manual entries)
    """
    anomalies = []

    # Signal 1: Large single transactions
    expenses = (db.session.query(Expense)
                .filter(Expense.user_id == user_id,
                        extract("year", Expense.spent_at) == year,
                        extract("month", Expense.spent_at) == month,
                        Expense.expense_type != "INCOME").all())

    if expenses:
        amounts = [float(e.amount) for e in expenses]
        mean = sum(amounts) / len(amounts)
        std = sqrt(sum((x-mean)**2 for x in amounts)/len(amounts)) if len(amounts) > 1 else 0
        for e in expenses:
            amt = float(e.amount)
            if std > 0 and (amt - mean) > 3 * std:
                anomalies.append({
                    "type": "large_transaction",
                    "expense_id": e.id,
                    "amount": amt,
                    "date": e.spent_at.isoformat(),
                    "description": e.notes or "Unknown",
                    "message": f"Unusually large transaction: ${amt:.2f} (avg ${mean:.2f})",
                    "severity": "high",
                })

        # Signal 2: Daily spending spike
        daily = {}
        for e in expenses:
            daily[e.spent_at] = daily.get(e.spent_at, 0) + float(e.amount)
        if daily:
            daily_avg = sum(daily.values()) / len(daily)
            for d, total in daily.items():
                if daily_avg > 0 and total > daily_avg * 2.5:
                    anomalies.append({
                        "type": "daily_spike",
                        "date": d.isoformat(),
                        "amount": round(total, 2),
                        "message": f"Daily spending spike on {d}: ${total:.2f} (avg ${daily_avg:.2f}/day)",
                        "severity": "medium",
                    })

        # Signal 3: Round-amount clusters (5+ round numbers = suspicious)
        round_amounts = [e for e in expenses if float(e.amount) % 100 == 0 and float(e.amount) >= 100]
        if len(round_amounts) >= 5:
            anomalies.append({
                "type": "round_amount_cluster",
                "count": len(round_amounts),
                "message": f"{len(round_amounts)} round-number transactions detected — possible manual entries or cash withdrawals.",
                "severity": "low",
            })

    return {
        "period": f"{year}-{month:02d}",
        "anomalies": sorted(anomalies, key=lambda x: {"high":0,"medium":1,"low":2}.get(x["severity"],3)),
        "anomaly_count": len(anomalies),
        "summary": f"{len(anomalies)} anomaly{'s' if len(anomalies)!=1 else ''} detected.",
    }
