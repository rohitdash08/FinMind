"""Lifestyle inflation detection insights."""

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.lifestyle_inflation")


def detect_lifestyle_inflation(user_id: int, months: int = 6) -> dict:
    """Detect lifestyle inflation by comparing monthly spending trends.

    Analyzes month-over-month spending growth to identify gradual
    increases that indicate lifestyle inflation.
    """
    today = date.today()
    monthly_totals = []

    for i in range(months):
        month_end = today.replace(day=1) - timedelta(days=1) if i == 0 else \
            (today.replace(day=1) - timedelta(days=30 * i))
        month_start = month_end.replace(day=1)

        # Simplified: use 30-day windows
        end = today - timedelta(days=30 * i)
        start = end - timedelta(days=30)

        total = (
            db.session.query(db.func.coalesce(db.func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.spent_at >= start,
                Expense.spent_at < end,
                Expense.expense_type == "EXPENSE",
            )
            .scalar()
        )
        monthly_totals.append({"period_end": end.isoformat(), "total": float(total or 0)})

    monthly_totals.reverse()  # oldest first

    # Calculate growth rates
    growth_rates = []
    for i in range(1, len(monthly_totals)):
        prev = monthly_totals[i - 1]["total"]
        curr = monthly_totals[i]["total"]
        if prev > 0:
            rate = (curr - prev) / prev * 100
            growth_rates.append(round(rate, 1))

    avg_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0
    consecutive_increases = 0
    for r in reversed(growth_rates):
        if r > 0:
            consecutive_increases += 1
        else:
            break

    # Determine inflation severity
    if avg_growth > 10 and consecutive_increases >= 3:
        severity = "high"
        message = f"Spending has grown {avg_growth:.1f}% monthly for {consecutive_increases} consecutive months"
    elif avg_growth > 5:
        severity = "moderate"
        message = f"Average monthly spending growth of {avg_growth:.1f}%"
    elif avg_growth > 0:
        severity = "low"
        message = "Slight upward trend in spending"
    else:
        severity = "none"
        message = "No lifestyle inflation detected"

    return {
        "severity": severity,
        "message": message,
        "avg_monthly_growth_pct": round(avg_growth, 1),
        "consecutive_increase_months": consecutive_increases,
        "monthly_totals": monthly_totals,
        "growth_rates": growth_rates,
    }
