"""Savings opportunity detection engine.

Analyzes spending patterns to identify potential savings opportunities
such as recurring overcharges, cheaper alternatives, unused subscriptions,
and spending anomalies.
"""

from datetime import date, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


def detect_opportunities(user_id: int, months: int = 3) -> dict:
    """Analyze recent spending and return savings opportunities."""
    end = date.today()
    start = end - timedelta(days=months * 30)

    expenses = (
        db.session.query(Expense, Category.name)
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .order_by(Expense.date)
        .all()
    )

    if not expenses:
        return {"opportunities": [], "potential_monthly_savings": 0, "analysis_period_days": months * 30}

    opportunities = []
    opportunities.extend(_detect_recurring_spikes(expenses))
    opportunities.extend(_detect_high_frequency_small(expenses))
    opportunities.extend(_detect_category_concentration(expenses))
    opportunities.extend(_detect_weekend_spending(expenses))

    potential = sum(o["estimated_monthly_savings"] for o in opportunities)

    return {
        "opportunities": sorted(opportunities, key=lambda x: x["estimated_monthly_savings"], reverse=True),
        "potential_monthly_savings": round(potential, 2),
        "analysis_period_days": months * 30,
        "total_expenses_analyzed": len(expenses),
    }


def _detect_recurring_spikes(expenses: list) -> list:
    """Find categories with spending spikes (>2x average)."""
    from collections import defaultdict

    monthly = defaultdict(lambda: defaultdict(float))
    for exp, cat_name in expenses:
        key = exp.date.strftime("%Y-%m")
        monthly[cat_name][key] += float(exp.amount)

    opportunities = []
    for cat, months_data in monthly.items():
        if len(months_data) < 2:
            continue
        values = list(months_data.values())
        avg = sum(values) / len(values)
        latest = values[-1]
        if avg > 0 and latest > avg * 2:
            savings = round(latest - avg, 2)
            opportunities.append({
                "type": "recurring_spike",
                "category": cat,
                "description": f"{cat} spending last month ({latest:.0f}) was {latest/avg:.1f}x the average ({avg:.0f})",
                "estimated_monthly_savings": savings,
                "confidence": "medium",
            })
    return opportunities


def _detect_high_frequency_small(expenses: list) -> list:
    """Detect frequent small purchases that add up."""
    from collections import defaultdict

    cat_expenses = defaultdict(list)
    for exp, cat_name in expenses:
        cat_expenses[cat_name].append(float(exp.amount))

    opportunities = []
    for cat, amounts in cat_expenses.items():
        small = [a for a in amounts if a < 50]
        if len(small) >= 15:
            total = sum(small)
            avg_monthly = total / 3
            if avg_monthly > 200:
                opportunities.append({
                    "type": "frequent_small_purchases",
                    "category": cat,
                    "description": f"{len(small)} small purchases in {cat} totaling {total:.0f}. Consider batching or reducing.",
                    "estimated_monthly_savings": round(avg_monthly * 0.2, 2),
                    "confidence": "low",
                })
    return opportunities


def _detect_category_concentration(expenses: list) -> list:
    """Flag if one category dominates spending (>50%)."""
    from collections import defaultdict

    totals = defaultdict(float)
    for exp, cat_name in expenses:
        totals[cat_name] += float(exp.amount)

    grand_total = sum(totals.values())
    if grand_total == 0:
        return []

    opportunities = []
    for cat, total in totals.items():
        pct = total / grand_total * 100
        if pct > 50:
            opportunities.append({
                "type": "category_concentration",
                "category": cat,
                "description": f"{cat} accounts for {pct:.0f}% of all spending ({total:.0f}). Diversifying may reveal savings.",
                "estimated_monthly_savings": round(total / 3 * 0.1, 2),
                "confidence": "low",
            })
    return opportunities


def _detect_weekend_spending(expenses: list) -> list:
    """Compare weekend vs weekday spending patterns."""
    weekend_total = 0
    weekday_total = 0
    weekend_count = 0
    weekday_count = 0

    for exp, _ in expenses:
        if exp.date.weekday() >= 5:
            weekend_total += float(exp.amount)
            weekend_count += 1
        else:
            weekday_total += float(exp.amount)
            weekday_count += 1

    if weekend_count == 0 or weekday_count == 0:
        return []

    weekend_avg = weekend_total / weekend_count
    weekday_avg = weekday_total / weekday_count

    if weekend_avg > weekday_avg * 1.5:
        monthly_excess = (weekend_avg - weekday_avg) * 8  # ~8 weekend days/month
        return [{
            "type": "weekend_spending",
            "category": "all",
            "description": f"Weekend spending avg ({weekend_avg:.0f}/tx) is {weekend_avg/weekday_avg:.1f}x weekday ({weekday_avg:.0f}/tx)",
            "estimated_monthly_savings": round(monthly_excess * 0.3, 2),
            "confidence": "medium",
        }]
    return []
