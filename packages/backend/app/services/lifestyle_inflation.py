"""Lifestyle inflation detection insights.

Tracks spending growth over time to identify lifestyle inflation —
when expenses rise faster than income, eroding savings potential.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from collections import defaultdict


class InflationSeverity:
    NONE = "none"
    MILD = "mild"           # 5-15% increase
    MODERATE = "moderate"   # 15-30% increase
    SEVERE = "severe"       # >30% increase


def detect_lifestyle_inflation(
    expenses: List[dict],
    income_monthly: Optional[float] = None,
    months: int = 6,
) -> dict:
    """Analyze spending trends to detect lifestyle inflation.

    Args:
        expenses: List with amount, category_name, spent_at.
        income_monthly: Optional monthly income for savings rate calc.
        months: Number of months to analyze.

    Returns:
        Inflation analysis with severity, trends, and recommendations.
    """
    monthly = _group_by_month(expenses, months)
    if len(monthly) < 2:
        return {
            "severity": InflationSeverity.NONE,
            "message": "Not enough data. Need at least 2 months of expenses.",
            "monthly_totals": [],
            "category_trends": [],
            "recommendations": [],
        }

    sorted_months = sorted(monthly.keys())
    totals = [{"month": m, "total": sum(float(e.get("amount", 0)) for e in monthly[m])} for m in sorted_months]

    first_half = totals[:len(totals)//2]
    second_half = totals[len(totals)//2:]
    avg_early = sum(t["total"] for t in first_half) / len(first_half) if first_half else 0
    avg_recent = sum(t["total"] for t in second_half) / len(second_half) if second_half else 0

    if avg_early > 0:
        growth_pct = (avg_recent - avg_early) / avg_early * 100
    else:
        growth_pct = 0

    severity = _classify_severity(growth_pct)
    category_trends = _analyze_category_trends(monthly, sorted_months)
    savings_impact = _calculate_savings_impact(avg_early, avg_recent, income_monthly)
    recommendations = _generate_recommendations(severity, growth_pct, category_trends, savings_impact)

    return {
        "severity": severity,
        "spending_growth_pct": round(growth_pct, 1),
        "avg_monthly_early": round(avg_early, 2),
        "avg_monthly_recent": round(avg_recent, 2),
        "monthly_increase": round(avg_recent - avg_early, 2),
        "monthly_totals": totals,
        "category_trends": category_trends[:10],
        "savings_impact": savings_impact,
        "recommendations": recommendations,
    }


def _group_by_month(expenses: List[dict], months: int) -> Dict[str, List[dict]]:
    cutoff = date.today() - timedelta(days=months * 31)
    monthly = defaultdict(list)
    for e in expenses:
        spent_at = e.get("spent_at")
        if isinstance(spent_at, str):
            try:
                spent_at = date.fromisoformat(spent_at[:10])
            except (ValueError, TypeError):
                continue
        if spent_at and spent_at >= cutoff:
            key = spent_at.strftime("%Y-%m")
            monthly[key].append(e)
    return monthly


def _classify_severity(growth_pct: float) -> str:
    if growth_pct < 5:
        return InflationSeverity.NONE
    elif growth_pct < 15:
        return InflationSeverity.MILD
    elif growth_pct < 30:
        return InflationSeverity.MODERATE
    else:
        return InflationSeverity.SEVERE


def _analyze_category_trends(monthly: dict, sorted_months: list) -> List[dict]:
    if len(sorted_months) < 2:
        return []

    mid = len(sorted_months) // 2
    early_months = sorted_months[:mid]
    recent_months = sorted_months[mid:]

    early_cats = defaultdict(float)
    recent_cats = defaultdict(float)

    for m in early_months:
        for e in monthly[m]:
            cat = e.get("category_name", "uncategorized")
            early_cats[cat] += float(e.get("amount", 0))

    for m in recent_months:
        for e in monthly[m]:
            cat = e.get("category_name", "uncategorized")
            recent_cats[cat] += float(e.get("amount", 0))

    # Normalize to monthly averages
    early_divisor = len(early_months) or 1
    recent_divisor = len(recent_months) or 1

    all_cats = set(list(early_cats.keys()) + list(recent_cats.keys()))
    trends = []
    for cat in all_cats:
        early_avg = early_cats.get(cat, 0) / early_divisor
        recent_avg = recent_cats.get(cat, 0) / recent_divisor
        if early_avg > 0:
            change_pct = (recent_avg - early_avg) / early_avg * 100
        elif recent_avg > 0:
            change_pct = 100
        else:
            change_pct = 0

        trends.append({
            "category": cat,
            "early_monthly_avg": round(early_avg, 2),
            "recent_monthly_avg": round(recent_avg, 2),
            "change_pct": round(change_pct, 1),
            "monthly_increase": round(recent_avg - early_avg, 2),
        })

    return sorted(trends, key=lambda x: abs(x["change_pct"]), reverse=True)


def _calculate_savings_impact(avg_early: float, avg_recent: float, income: Optional[float]) -> dict:
    monthly_diff = avg_recent - avg_early
    annual_impact = monthly_diff * 12

    result = {
        "monthly_extra_spending": round(monthly_diff, 2),
        "annual_impact": round(annual_impact, 2),
    }

    if income and income > 0:
        early_savings_rate = max(0, (income - avg_early) / income * 100)
        recent_savings_rate = max(0, (income - avg_recent) / income * 100)
        result["early_savings_rate"] = round(early_savings_rate, 1)
        result["recent_savings_rate"] = round(recent_savings_rate, 1)
        result["savings_rate_change"] = round(recent_savings_rate - early_savings_rate, 1)

    return result


def _generate_recommendations(severity: str, growth_pct: float, trends: list, savings: dict) -> List[str]:
    recs = []

    if severity == InflationSeverity.NONE:
        recs.append("Your spending is stable. Great job keeping lifestyle inflation in check!")
        return recs

    if severity == InflationSeverity.SEVERE:
        recs.append(f"Spending increased {growth_pct:.0f}% — this is significant lifestyle inflation. Immediate review recommended.")
    elif severity == InflationSeverity.MODERATE:
        recs.append(f"Spending up {growth_pct:.0f}%. Consider reviewing discretionary categories.")
    else:
        recs.append(f"Mild spending increase of {growth_pct:.0f}%. Worth monitoring.")

    # Top growing categories
    growing = [t for t in trends if t["change_pct"] > 20 and t["monthly_increase"] > 10][:3]
    if growing:
        names = ", ".join(t["category"] for t in growing)
        recs.append(f"Fastest growing categories: {names}. Set budgets for these.")

    if savings.get("savings_rate_change", 0) < -5:
        recs.append(f"Savings rate dropped {abs(savings['savings_rate_change']):.1f}%. Automate savings before spending.")

    annual = savings.get("annual_impact", 0)
    if annual > 500:
        recs.append(f"Extra ${annual:.0f}/year in spending. Redirecting even half to savings would compound significantly.")

    return recs
