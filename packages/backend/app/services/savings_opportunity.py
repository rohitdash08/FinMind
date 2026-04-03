"""
Savings Opportunity Detection Engine (#119)
Identifies areas where users can reduce spending based on patterns,
benchmarks, and behavioral analysis.
"""
from datetime import date, timedelta
from typing import Any
from sqlalchemy import func, text
from ..extensions import db
from ..models import Expense, Category, RecurringExpense


# Category benchmark ratios (% of total spending) - financial planning defaults
CATEGORY_BENCHMARKS = {
    "food": 0.15,
    "dining": 0.05,
    "restaurant": 0.05,
    "entertainment": 0.05,
    "subscriptions": 0.05,
    "shopping": 0.10,
    "transport": 0.10,
    "travel": 0.08,
    "clothing": 0.05,
    "alcohol": 0.03,
    "coffee": 0.02,
    "delivery": 0.04,
    "gym": 0.02,
    "beauty": 0.03,
}

ESSENTIAL_KEYWORDS = {
    "rent", "mortgage", "insurance", "utilities", "electricity", "water",
    "gas", "internet", "medical", "health", "medicine", "education", "loan",
    "tax", "groceries", "grocery"
}

DISCRETIONARY_KEYWORDS = {
    "entertainment", "gaming", "movie", "netflix", "spotify", "amazon prime",
    "dining", "restaurant", "bar", "coffee", "starbucks", "fast food",
    "shopping", "clothing", "fashion", "travel", "vacation", "hotel",
    "alcohol", "beer", "wine", "beauty", "salon", "gym", "sports",
    "subscription", "delivery", "zomato", "swiggy", "uber eats"
}


def _is_essential(category_name: str) -> bool:
    """Check if a category is essential based on keywords."""
    name_lower = (category_name or "").lower()
    return any(kw in name_lower for kw in ESSENTIAL_KEYWORDS)


def _is_discretionary(category_name: str) -> bool:
    """Check if a category is discretionary based on keywords."""
    name_lower = (category_name or "").lower()
    return any(kw in name_lower for kw in DISCRETIONARY_KEYWORDS)


def _get_benchmark_ratio(category_name: str) -> float | None:
    """Return the benchmark spending ratio for a category."""
    name_lower = (category_name or "").lower()
    for kw, ratio in CATEGORY_BENCHMARKS.items():
        if kw in name_lower:
            return ratio
    return None


def detect_savings_opportunities(user_id: int, months: int = 3) -> dict[str, Any]:
    """
    Analyze user spending patterns and detect savings opportunities.

    Args:
        user_id: The user ID to analyze
        months: Number of months to analyze (default: 3)

    Returns:
        Dictionary with opportunities, potential savings, and recommendations
    """
    today = date.today()
    start_date = today - timedelta(days=30 * months)

    # Fetch expenses with category names
    rows = (
        db.session.query(
            Expense.amount,
            Expense.spent_at,
            Expense.notes,
            Category.name.label("category_name"),
        )
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start_date,
        )
        .all()
    )

    if not rows:
        return {
            "opportunities": [],
            "total_potential_savings": 0.0,
            "monthly_spend_avg": 0.0,
            "total_spend_analyzed": 0.0,
            "summary": "Not enough data to detect savings opportunities.",
            "analysis_period_months": months,
        }

    total_spend = sum(float(r.amount) for r in rows)
    monthly_avg = total_spend / max(months, 1)

    # Group by category
    cat_totals: dict[str, float] = {}
    cat_counts: dict[str, int] = {}
    for r in rows:
        cat = r.category_name or "Uncategorized"
        cat_totals[cat] = cat_totals.get(cat, 0.0) + float(r.amount)
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    opportunities = []

    # Opportunity 1: Categories exceeding benchmarks
    for cat, total in cat_totals.items():
        ratio = total / total_spend if total_spend > 0 else 0
        benchmark = _get_benchmark_ratio(cat)
        if benchmark and ratio > benchmark * 1.5:
            excess = total - (benchmark * total_spend)
            monthly_excess = excess / months
            opportunities.append({
                "type": "over_benchmark",
                "category": cat,
                "severity": "high" if ratio > benchmark * 2 else "medium",
                "current_ratio": round(ratio * 100, 1),
                "benchmark_ratio": round(benchmark * 100, 1),
                "potential_monthly_savings": round(monthly_excess, 2),
                "recommendation": (
                    f"Reduce {cat} spending from {ratio*100:.1f}% to "
                    f"{benchmark*100:.0f}% of total budget. "
                    f"Potential savings: {monthly_excess:.0f}/month."
                ),
            })

    # Opportunity 2: High discretionary spending
    discretionary_total = sum(
        total for cat, total in cat_totals.items()
        if _is_discretionary(cat) and not _is_essential(cat)
    )
    discretionary_ratio = discretionary_total / total_spend if total_spend > 0 else 0
    if discretionary_ratio > 0.35:
        target_discretionary = total_spend * 0.25
        monthly_saving = (discretionary_total - target_discretionary) / months
        opportunities.append({
            "type": "high_discretionary",
            "category": "Discretionary Spending",
            "severity": "high" if discretionary_ratio > 0.5 else "medium",
            "current_ratio": round(discretionary_ratio * 100, 1),
            "benchmark_ratio": 25.0,
            "potential_monthly_savings": round(monthly_saving, 2),
            "recommendation": (
                f"Discretionary spending is {discretionary_ratio*100:.1f}% of total. "
                f"Target 25% for better savings. Potential: {monthly_saving:.0f}/month."
            ),
        })

    # Opportunity 3: Top spending categories by absolute value
    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    for cat, total in sorted_cats[:3]:
        if not _is_essential(cat) and total / months > 500:
            monthly_cat = total / months
            potential_saving = monthly_cat * 0.20  # 20% reduction target
            # Avoid duplicate if already added
            if not any(o["category"] == cat for o in opportunities):
                opportunities.append({
                    "type": "top_spender",
                    "category": cat,
                    "severity": "low",
                    "current_ratio": round((total / total_spend) * 100, 1),
                    "benchmark_ratio": None,
                    "potential_monthly_savings": round(potential_saving, 2),
                    "recommendation": (
                        f"{cat} is a top spending category at {monthly_cat:.0f}/month. "
                        f"A 20% reduction saves {potential_saving:.0f}/month."
                    ),
                })

    # Opportunity 4: Subscription clustering
    subscription_keywords = ["netflix", "spotify", "amazon", "subscription", "prime", "youtube"]
    subscription_expenses = [
        r for r in rows
        if any(kw in (r.notes or "").lower() for kw in subscription_keywords)
        or any(kw in (r.category_name or "").lower() for kw in ["subscription"])
    ]
    if len(subscription_expenses) >= 3:
        sub_total = sum(float(r.amount) for r in subscription_expenses)
        sub_monthly = sub_total / months
        if sub_monthly > 1000:
            opportunities.append({
                "type": "subscription_audit",
                "category": "Subscriptions",
                "severity": "medium",
                "current_ratio": round((sub_total / total_spend) * 100, 1),
                "benchmark_ratio": 5.0,
                "potential_monthly_savings": round(sub_monthly * 0.30, 2),
                "recommendation": (
                    f"Found {len(subscription_expenses)} subscription-type expenses "
                    f"totaling {sub_monthly:.0f}/month. "
                    f"Audit and cancel unused subscriptions to save 30%."
                ),
            })

    # Sort opportunities by potential savings
    opportunities.sort(key=lambda x: x["potential_monthly_savings"], reverse=True)

    total_potential = sum(o["potential_monthly_savings"] for o in opportunities)

    return {
        "opportunities": opportunities,
        "total_potential_savings": round(total_potential, 2),
        "monthly_spend_avg": round(monthly_avg, 2),
        "total_spend_analyzed": round(total_spend, 2),
        "analysis_period_months": months,
        "summary": (
            f"Found {len(opportunities)} savings opportunities. "
            f"Potential monthly savings: {total_potential:.0f} "
            f"out of {monthly_avg:.0f} average monthly spend."
            if opportunities
            else "No significant savings opportunities detected. Great financial discipline!"
        ),
    }
