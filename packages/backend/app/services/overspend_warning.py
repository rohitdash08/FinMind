"""Category overspend early warning system.

Monitors spending against budgets and historical averages to provide
early warnings before categories exceed their limits.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from collections import defaultdict


class AlertLevel:
    SAFE = "safe"           # <70% of budget
    CAUTION = "caution"     # 70-85% of budget
    WARNING = "warning"     # 85-100% of budget
    EXCEEDED = "exceeded"   # >100% of budget


def check_overspend(
    expenses: List[dict],
    budgets: Dict[str, float],
    period_start: Optional[str] = None,
    period_end: Optional[str] = None,
) -> dict:
    """Check spending against category budgets.

    Args:
        expenses: List with amount, category_name, spent_at.
        budgets: Dict of {category_name: monthly_budget_amount}.
        period_start: Start date (default: 1st of current month).
        period_end: End date (default: today).

    Returns:
        Overspend analysis with alerts and projections.
    """
    today = date.today()
    if period_start:
        start = date.fromisoformat(period_start)
    else:
        start = today.replace(day=1)
    if period_end:
        end = date.fromisoformat(period_end)
    else:
        end = today

    days_elapsed = max((end - start).days, 1)
    days_in_month = 30
    pace_factor = days_in_month / days_elapsed

    # Sum expenses by category in period
    category_spent = defaultdict(float)
    category_count = defaultdict(int)
    for e in expenses:
        spent_at = _parse_date(e.get("spent_at"))
        if spent_at and start <= spent_at <= end:
            cat = e.get("category_name", "uncategorized")
            category_spent[cat] += float(e.get("amount", 0))
            category_count[cat] += 1

    alerts = []
    for category, budget in budgets.items():
        if budget <= 0:
            continue
        spent = category_spent.get(category, 0)
        pct_used = (spent / budget) * 100 if budget > 0 else 0
        projected = spent * pace_factor
        projected_pct = (projected / budget) * 100 if budget > 0 else 0
        remaining = max(budget - spent, 0)
        daily_remaining = remaining / max((days_in_month - days_elapsed), 1)

        level = _classify_alert(pct_used)
        projected_level = _classify_alert(projected_pct)

        alert = {
            "category": category,
            "budget": budget,
            "spent": round(spent, 2),
            "remaining": round(remaining, 2),
            "pct_used": round(pct_used, 1),
            "level": level,
            "projected_total": round(projected, 2),
            "projected_pct": round(projected_pct, 1),
            "projected_level": projected_level,
            "daily_budget_remaining": round(daily_remaining, 2),
            "transactions": category_count.get(category, 0),
        }

        if level in [AlertLevel.WARNING, AlertLevel.EXCEEDED] or projected_level == AlertLevel.EXCEEDED:
            alert["action_needed"] = True
        else:
            alert["action_needed"] = False

        alerts.append(alert)

    # Sort: exceeded first, then warning, caution, safe
    level_order = {AlertLevel.EXCEEDED: 0, AlertLevel.WARNING: 1, AlertLevel.CAUTION: 2, AlertLevel.SAFE: 3}
    alerts.sort(key=lambda a: level_order.get(a["level"], 4))

    exceeded = [a for a in alerts if a["level"] == AlertLevel.EXCEEDED]
    warnings = [a for a in alerts if a["level"] == AlertLevel.WARNING]
    cautions = [a for a in alerts if a["level"] == AlertLevel.CAUTION]

    # Unbudgeted spending
    unbudgeted = {}
    for cat, spent in category_spent.items():
        if cat not in budgets:
            unbudgeted[cat] = round(spent, 2)

    return {
        "period": {"start": str(start), "end": str(end), "days_elapsed": days_elapsed},
        "alerts": alerts,
        "summary": {
            "total_budgeted": round(sum(budgets.values()), 2),
            "total_spent": round(sum(category_spent.values()), 2),
            "exceeded_count": len(exceeded),
            "warning_count": len(warnings),
            "caution_count": len(cautions),
            "categories_tracked": len(budgets),
        },
        "unbudgeted_spending": unbudgeted,
        "recommendations": _generate_alerts(alerts, unbudgeted),
    }


def _classify_alert(pct: float) -> str:
    if pct >= 100:
        return AlertLevel.EXCEEDED
    elif pct >= 85:
        return AlertLevel.WARNING
    elif pct >= 70:
        return AlertLevel.CAUTION
    return AlertLevel.SAFE


def _generate_alerts(alerts: list, unbudgeted: dict) -> List[str]:
    recs = []
    exceeded = [a for a in alerts if a["level"] == AlertLevel.EXCEEDED]
    if exceeded:
        names = ", ".join(a["category"] for a in exceeded)
        recs.append(f"Budget exceeded in: {names}. Review and adjust spending or increase budget.")

    projected_over = [a for a in alerts if a["projected_level"] == AlertLevel.EXCEEDED and a["level"] != AlertLevel.EXCEEDED]
    if projected_over:
        names = ", ".join(a["category"] for a in projected_over)
        recs.append(f"On track to exceed budget: {names}. Reduce spending now to stay on target.")

    warnings = [a for a in alerts if a["level"] == AlertLevel.WARNING]
    for w in warnings:
        recs.append(f"{w['category']}: ${w['daily_budget_remaining']:.2f}/day remaining to stay within budget.")

    if unbudgeted and sum(unbudgeted.values()) > 50:
        recs.append(f"${sum(unbudgeted.values()):.0f} in unbudgeted categories. Consider setting budgets for: {', '.join(list(unbudgeted.keys())[:3])}")

    if not recs:
        recs.append("All categories within budget. Keep it up!")

    return recs


def _parse_date(val) -> Optional[date]:
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val[:10])
        except (ValueError, TypeError):
            return None
    return None
