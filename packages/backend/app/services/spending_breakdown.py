"""Essential vs discretionary spending breakdown.

Classifies expenses into essential (needs) and discretionary (wants)
categories, providing insights for better financial decisions.
"""

from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Tuple
from collections import defaultdict


class SpendingType(str, Enum):
    ESSENTIAL = "essential"       # Needs: rent, utilities, groceries, insurance
    DISCRETIONARY = "discretionary"  # Wants: dining, entertainment, shopping
    SAVINGS = "savings"           # Investments, emergency fund
    UNCLASSIFIED = "unclassified"


# Default classification rules by category name patterns
CLASSIFICATION_RULES = {
    SpendingType.ESSENTIAL: [
        "rent", "mortgage", "utilities", "electricity", "water", "gas",
        "groceries", "food", "insurance", "health", "medical", "pharmacy",
        "transport", "fuel", "petrol", "internet", "phone", "childcare",
        "education", "tuition", "tax", "loan", "debt",
    ],
    SpendingType.DISCRETIONARY: [
        "dining", "restaurant", "cafe", "coffee", "entertainment",
        "movies", "streaming", "subscription", "shopping", "clothing",
        "fashion", "beauty", "gym", "fitness", "travel", "vacation",
        "hobby", "gaming", "alcohol", "bar", "gifts", "luxury",
    ],
    SpendingType.SAVINGS: [
        "savings", "investment", "emergency", "retirement", "stocks",
        "crypto", "deposit",
    ],
}


def classify_category(category_name: str, custom_rules: Optional[dict] = None) -> SpendingType:
    """Classify a category name into spending type.

    Args:
        category_name: The category name to classify.
        custom_rules: Optional user-defined overrides {category_name: SpendingType}.

    Returns:
        SpendingType classification.
    """
    name_lower = category_name.lower().strip()

    # Check custom rules first
    if custom_rules and name_lower in custom_rules:
        return SpendingType(custom_rules[name_lower])

    for spending_type, keywords in CLASSIFICATION_RULES.items():
        for keyword in keywords:
            if keyword in name_lower:
                return spending_type

    return SpendingType.UNCLASSIFIED


def analyze_spending_breakdown(
    expenses: List[dict],
    custom_rules: Optional[dict] = None,
) -> dict:
    """Analyze expenses and break down into essential vs discretionary.

    Args:
        expenses: List of expense dicts with 'amount', 'category_name', 'spent_at'.
        custom_rules: Optional classification overrides.

    Returns:
        Breakdown analysis with totals, percentages, and recommendations.
    """
    totals = defaultdict(Decimal)
    by_category = defaultdict(lambda: {"amount": Decimal("0"), "count": 0, "type": None})

    for exp in expenses:
        amount = Decimal(str(exp.get("amount", 0)))
        cat_name = exp.get("category_name", "uncategorized")
        spending_type = classify_category(cat_name, custom_rules)

        totals[spending_type.value] += amount
        by_category[cat_name]["amount"] += amount
        by_category[cat_name]["count"] += 1
        by_category[cat_name]["type"] = spending_type.value

    grand_total = sum(totals.values()) or Decimal("1")

    breakdown = {}
    for stype in SpendingType:
        amount = totals.get(stype.value, Decimal("0"))
        breakdown[stype.value] = {
            "amount": float(amount),
            "percentage": round(float(amount / grand_total * 100), 1),
        }

    # Category details sorted by amount
    categories = []
    for name, data in sorted(by_category.items(), key=lambda x: x[1]["amount"], reverse=True):
        categories.append({
            "name": name,
            "amount": float(data["amount"]),
            "count": data["count"],
            "type": data["type"],
            "percentage": round(float(data["amount"] / grand_total * 100), 1),
        })

    # 50/30/20 rule analysis
    rule_analysis = _analyze_50_30_20(breakdown, float(grand_total))

    return {
        "total_spending": float(grand_total),
        "breakdown": breakdown,
        "categories": categories,
        "rule_50_30_20": rule_analysis,
        "recommendations": _generate_recommendations(breakdown, categories),
    }


def _analyze_50_30_20(breakdown: dict, total: float) -> dict:
    """Analyze against the 50/30/20 budgeting rule.

    50% needs, 30% wants, 20% savings.
    """
    essential_pct = breakdown.get("essential", {}).get("percentage", 0)
    discretionary_pct = breakdown.get("discretionary", {}).get("percentage", 0)
    savings_pct = breakdown.get("savings", {}).get("percentage", 0)

    return {
        "essential": {
            "actual": essential_pct,
            "target": 50,
            "status": "on_track" if essential_pct <= 55 else "over",
            "diff": round(essential_pct - 50, 1),
        },
        "discretionary": {
            "actual": discretionary_pct,
            "target": 30,
            "status": "on_track" if discretionary_pct <= 35 else "over",
            "diff": round(discretionary_pct - 30, 1),
        },
        "savings": {
            "actual": savings_pct,
            "target": 20,
            "status": "on_track" if savings_pct >= 15 else "under",
            "diff": round(savings_pct - 20, 1),
        },
    }


def _generate_recommendations(breakdown: dict, categories: list) -> List[str]:
    """Generate actionable recommendations based on spending patterns."""
    recs = []

    essential_pct = breakdown.get("essential", {}).get("percentage", 0)
    discretionary_pct = breakdown.get("discretionary", {}).get("percentage", 0)
    savings_pct = breakdown.get("savings", {}).get("percentage", 0)
    unclassified_pct = breakdown.get("unclassified", {}).get("percentage", 0)

    if essential_pct > 60:
        recs.append("Essential spending is above 60%. Review fixed costs for potential savings (insurance, utilities, subscriptions).")

    if discretionary_pct > 40:
        top_disc = [c for c in categories if c["type"] == "discretionary"][:3]
        if top_disc:
            names = ", ".join(c["name"] for c in top_disc)
            recs.append(f"Discretionary spending is high. Top areas: {names}. Consider setting category budgets.")

    if savings_pct < 10:
        recs.append("Savings rate is below 10%. Try automating a fixed amount to savings each month.")
    elif savings_pct < 20:
        recs.append("Savings rate is below the recommended 20%. Small increases can compound significantly.")

    if unclassified_pct > 15:
        recs.append(f"{unclassified_pct}% of spending is unclassified. Categorize these for better insights.")

    if not recs:
        recs.append("Your spending balance looks healthy! Keep it up.")

    return recs


def get_monthly_trend(
    expenses: List[dict],
    months: int = 6,
    custom_rules: Optional[dict] = None,
) -> List[dict]:
    """Get monthly essential vs discretionary trend.

    Args:
        expenses: All expenses with 'amount', 'category_name', 'spent_at'.
        months: Number of months to analyze.
        custom_rules: Optional classification overrides.

    Returns:
        List of monthly breakdowns.
    """
    today = date.today()
    monthly = defaultdict(list)

    for exp in expenses:
        spent_at = exp.get("spent_at")
        if isinstance(spent_at, str):
            spent_at = date.fromisoformat(spent_at)
        if spent_at and (today - spent_at).days <= months * 31:
            month_key = spent_at.strftime("%Y-%m")
            monthly[month_key].append(exp)

    trend = []
    for month_key in sorted(monthly.keys()):
        analysis = analyze_spending_breakdown(monthly[month_key], custom_rules)
        trend.append({
            "month": month_key,
            "total": analysis["total_spending"],
            "essential": analysis["breakdown"]["essential"]["amount"],
            "discretionary": analysis["breakdown"]["discretionary"]["amount"],
            "savings": analysis["breakdown"]["savings"]["amount"],
            "essential_pct": analysis["breakdown"]["essential"]["percentage"],
            "discretionary_pct": analysis["breakdown"]["discretionary"]["percentage"],
        })

    return trend
