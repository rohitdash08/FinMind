"""Savings opportunity detection engine."""

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense
import logging

logger = logging.getLogger("finmind.savings_opportunities")


def detect_opportunities(user_id: int) -> list[dict]:
    """Detect potential savings opportunities from spending patterns."""
    opportunities = []
    today = date.today()
    last_30 = today - timedelta(days=30)
    last_60 = today - timedelta(days=60)

    recent = (
        db.session.query(Expense)
        .filter(Expense.user_id == user_id, Expense.spent_at >= last_30)
        .all()
    )
    previous = (
        db.session.query(Expense)
        .filter(Expense.user_id == user_id, Expense.spent_at >= last_60, Expense.spent_at < last_30)
        .all()
    )

    # 1. Detect unused subscriptions (charged but no related activity)
    recurring_notes = {}
    for e in recent:
        key = (e.notes or "").lower().strip()[:30]
        if key:
            recurring_notes.setdefault(key, []).append(e)

    for key, expenses in recurring_notes.items():
        if len(expenses) >= 2:
            total = sum(float(e.amount) for e in expenses)
            if total > 0:
                opportunities.append({
                    "type": "recurring_expense",
                    "description": f"Recurring charge: {expenses[0].notes or key}",
                    "monthly_cost": round(total, 2),
                    "potential_annual_savings": round(total * 12, 2),
                    "suggestion": "Review if this subscription is still needed",
                })

    # 2. Detect spending spikes (categories with >50% increase)
    recent_total = sum(Decimal(str(e.amount)) for e in recent)
    prev_total = sum(Decimal(str(e.amount)) for e in previous)

    if prev_total > 0 and recent_total > prev_total * Decimal("1.5"):
        increase = float(recent_total - prev_total)
        opportunities.append({
            "type": "spending_spike",
            "description": "Overall spending increased 50%+ vs previous month",
            "monthly_cost": round(increase, 2),
            "potential_annual_savings": round(increase * 6, 2),
            "suggestion": "Review recent large purchases and cut back",
        })

    # 3. Detect small frequent purchases that add up
    small_frequent = {}
    for e in recent:
        if float(e.amount) < 50:
            cat = e.category_id or 0
            small_frequent.setdefault(cat, {"count": 0, "total": Decimal("0")})
            small_frequent[cat]["count"] += 1
            small_frequent[cat]["total"] += Decimal(str(e.amount))

    for cat_id, data in small_frequent.items():
        if data["count"] >= 10 and float(data["total"]) > 200:
            opportunities.append({
                "type": "small_frequent",
                "description": f"{data['count']} small purchases totaling {float(data['total']):.0f}",
                "monthly_cost": round(float(data["total"]), 2),
                "potential_annual_savings": round(float(data["total"]) * 6, 2),
                "suggestion": "Batch purchases or set a daily spending limit",
            })

    return sorted(opportunities, key=lambda o: -o["potential_annual_savings"])
