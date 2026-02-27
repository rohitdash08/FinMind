"""Lifestyle inflation detection insights.

Compares spending across time periods to detect gradual lifestyle inflation —
the tendency to spend more as income or comfort increases.
"""

from datetime import date, timedelta
from collections import defaultdict
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


def detect_inflation(user_id: int, months: int = 6) -> dict:
    """Analyze spending over *months* to detect lifestyle inflation trends."""
    end = date.today()
    start = end - timedelta(days=months * 30)

    rows = (
        db.session.query(
            func.extract("year", Expense.date).label("yr"),
            func.extract("month", Expense.date).label("mo"),
            Category.name,
            func.sum(Expense.amount),
            func.count(Expense.id),
        )
        .join(Category, Expense.category_id == Category.id)
        .filter(Expense.user_id == user_id, Expense.date >= start, Expense.date <= end)
        .group_by("yr", "mo", Category.name)
        .all()
    )

    if not rows:
        return {
            "inflation_detected": False,
            "overall_trend": "insufficient_data",
            "monthly_totals": [],
            "category_trends": [],
            "insights": [],
            "analysis_months": months,
        }

    # Build monthly totals
    monthly = defaultdict(lambda: {"total": 0, "categories": defaultdict(float), "tx_count": 0})
    for yr, mo, cat, total, count in rows:
        key = f"{int(yr)}-{int(mo):02d}"
        monthly[key]["total"] += float(total)
        monthly[key]["categories"][cat] += float(total)
        monthly[key]["tx_count"] += count

    sorted_months = sorted(monthly.keys())
    totals = [monthly[m]["total"] for m in sorted_months]

    # Overall trend
    overall = _compute_trend(totals)

    # Category-level trends
    all_cats = set()
    for m in monthly.values():
        all_cats.update(m["categories"].keys())

    cat_trends = []
    for cat in sorted(all_cats):
        cat_vals = [monthly[m]["categories"].get(cat, 0) for m in sorted_months]
        trend = _compute_trend(cat_vals)
        if trend["direction"] == "increasing" and trend["growth_rate"] > 10:
            cat_trends.append({
                "category": cat,
                "first_month": round(cat_vals[0], 2),
                "last_month": round(cat_vals[-1], 2),
                **trend,
            })

    cat_trends.sort(key=lambda x: x["growth_rate"], reverse=True)

    # Insights
    insights = _generate_insights(overall, cat_trends, totals)

    monthly_list = [
        {"month": m, "total": round(monthly[m]["total"], 2), "tx_count": monthly[m]["tx_count"]}
        for m in sorted_months
    ]

    return {
        "inflation_detected": overall["direction"] == "increasing" and overall["growth_rate"] > 15,
        "overall_trend": overall,
        "monthly_totals": monthly_list,
        "category_trends": cat_trends,
        "insights": insights,
        "analysis_months": len(sorted_months),
    }


def _compute_trend(values: list[float]) -> dict:
    if len(values) < 2:
        return {"direction": "insufficient_data", "growth_rate": 0}

    first_half = sum(values[:len(values)//2]) / max(len(values)//2, 1)
    second_half = sum(values[len(values)//2:]) / max(len(values) - len(values)//2, 1)

    if first_half == 0:
        rate = 100.0 if second_half > 0 else 0.0
    else:
        rate = round((second_half - first_half) / first_half * 100, 1)

    if rate > 5:
        direction = "increasing"
    elif rate < -5:
        direction = "decreasing"
    else:
        direction = "stable"

    return {"direction": direction, "growth_rate": rate}


def _generate_insights(overall: dict, cat_trends: list, totals: list) -> list[str]:
    insights = []

    if overall["direction"] == "increasing":
        if overall["growth_rate"] > 30:
            insights.append(
                f"⚠️ Significant lifestyle inflation detected: spending grew {overall['growth_rate']}% "
                "over the analysis period. Review discretionary categories."
            )
        elif overall["growth_rate"] > 15:
            insights.append(
                f"Moderate spending increase of {overall['growth_rate']}% detected. "
                "This may indicate lifestyle inflation creeping in."
            )
    elif overall["direction"] == "decreasing":
        insights.append(
            f"Spending decreased {abs(overall['growth_rate'])}%. You're keeping lifestyle inflation in check!"
        )

    for ct in cat_trends[:3]:
        if ct["growth_rate"] > 50:
            insights.append(
                f"{ct['category']} spending surged {ct['growth_rate']}% "
                f"(from {ct['first_month']:.0f} to {ct['last_month']:.0f}/month)."
            )

    if not insights:
        insights.append("Spending patterns are stable. No significant lifestyle inflation detected.")

    return insights
