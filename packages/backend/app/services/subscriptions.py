"""
Auto-detect subscriptions + subscription cost increase detection (issues #109, #110).
"""
import logging, re
from datetime import date
from decimal import Decimal
from sqlalchemy import func, extract
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.subscriptions")

SUBSCRIPTION_PATTERNS = [
    r"netflix", r"spotify", r"hulu", r"disney\+?", r"prime\s*video", r"apple\s*(tv|music|one)",
    r"youtube\s*premium", r"adobe", r"microsoft\s*(365|office)", r"google\s*(one|workspace)",
    r"dropbox", r"slack", r"notion", r"figma", r"github", r"openai", r"anthropic",
    r"gym", r"membership", r"subscription", r"monthly",
]

CADENCES = [7, 14, 28, 30, 31]  # weekly, biweekly, monthly variants


def detect_subscriptions(user_id: int, months: int = 3) -> list:
    """Find recurring charges that look like subscriptions."""
    from datetime import date
    from dateutil.relativedelta import relativedelta
    ref = date.today()
    start = ref - relativedelta(months=months)

    expenses = (db.session.query(Expense)
                .filter(Expense.user_id == user_id, Expense.spent_at >= start,
                        Expense.expense_type != "INCOME")
                .order_by(Expense.notes, Expense.amount, Expense.spent_at).all())

    # Group by (notes fingerprint, amount)
    groups: dict = {}
    for e in expenses:
        key = (re.sub(r'\d+', '', (e.notes or "").lower().strip())[:40], float(e.amount))
        groups.setdefault(key, []).append(e)

    subscriptions = []
    for (desc, amt), txns in groups.items():
        if len(txns) < 2: continue
        dates = sorted(t.spent_at for t in txns)
        gaps = [(dates[i+1]-dates[i]).days for i in range(len(dates)-1)]
        avg_gap = sum(gaps)/len(gaps) if gaps else 0
        is_sub = any(abs(avg_gap - c) <= 3 for c in CADENCES)
        is_named = any(re.search(p, desc, re.I) for p in SUBSCRIPTION_PATTERNS)
        if is_sub or is_named:
            subscriptions.append({
                "description": txns[0].notes or "",
                "amount": amt, "occurrences": len(txns),
                "avg_interval_days": round(avg_gap, 1),
                "cadence": "monthly" if avg_gap > 25 else "weekly" if avg_gap < 10 else "biweekly",
                "annual_cost": round(amt * (365 / avg_gap if avg_gap else 12), 2),
                "expense_ids": [t.id for t in txns],
            })
    return sorted(subscriptions, key=lambda x: -x["annual_cost"])


def detect_price_increases(user_id: int) -> list:
    """Find subscriptions where the amount increased between billing cycles."""
    expenses = (db.session.query(Expense)
                .filter(Expense.user_id == user_id, Expense.expense_type != "INCOME")
                .order_by(Expense.notes, Expense.spent_at).all())

    groups: dict = {}
    for e in expenses:
        key = re.sub(r'\d+', '', (e.notes or "").lower().strip())[:40]
        groups.setdefault(key, []).append(e)

    increases = []
    for desc, txns in groups.items():
        if len(txns) < 3: continue
        amounts = [float(t.amount) for t in sorted(txns, key=lambda x: x.spent_at)]
        # Check if last amount > median of previous amounts
        prev_avg = sum(amounts[:-1]) / len(amounts[:-1])
        last = amounts[-1]
        if last > prev_avg * 1.05:  # >5% increase
            increases.append({
                "description": txns[0].notes or desc,
                "previous_amount": round(prev_avg, 2),
                "new_amount": last,
                "increase_pct": round((last - prev_avg) / prev_avg * 100, 1),
                "detected_on": sorted(txns, key=lambda x: x.spent_at)[-1].spent_at.isoformat(),
            })
    return increases
