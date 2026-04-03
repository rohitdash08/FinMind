"""
Essential vs Discretionary Spending Breakdown (#120)
Classifies user expenses as essential or discretionary to highlight
financial priorities and potential savings areas.
"""
from datetime import date, timedelta
from typing import Any
from decimal import Decimal
from sqlalchemy import func
from ..extensions import db
from ..models import Expense, Category


# Essential spending keywords - non-negotiable necessities
ESSENTIAL_CATEGORIES = {
    "rent", "mortgage", "housing", "home loan",
    "electricity", "water", "gas", "utilities",
    "internet", "broadband", "mobile", "phone",
    "insurance", "health insurance", "life insurance",
    "medical", "medicine", "pharmacy", "doctor", "hospital",
    "groceries", "grocery", "supermarket", "vegetables", "dairy",
    "education", "school", "college", "tuition", "course fees",
    "loan emi", "loan", "emi", "repayment",
    "tax", "income tax", "gst",
    "childcare", "daycare",
    "transport", "commute", "bus", "metro", "fuel", "petrol",
}

# Discretionary spending keywords - lifestyle choices
DISCRETIONARY_CATEGORIES = {
    "entertainment", "cinema", "movie", "theatre",
    "dining", "restaurant", "café", "cafe", "bar", "pub",
    "fast food", "takeaway", "delivery", "zomato", "swiggy",
    "coffee", "starbucks", "tea",
    "shopping", "clothing", "fashion", "apparel", "accessories",
    "electronics", "gadgets",
    "travel", "vacation", "holiday", "hotel", "tourism",
    "gaming", "games", "playstation", "xbox",
    "beauty", "salon", "spa", "cosmetics", "makeup",
    "gym", "fitness", "sports", "yoga",
    "subscription", "netflix", "spotify", "amazon prime",
    "youtube", "disney", "hotstar",
    "alcohol", "beer", "wine", "liquor",
    "gifts", "presents",
    "personal care", "grooming",
    "social", "parties",
}

# Mixed categories (classify by amount thresholds)
MIXED_CATEGORIES = {"transport", "food"}


def _classify_category(category_name: str | None) -> str:
    """
    Classify a spending category as 'essential', 'discretionary', or 'mixed'.

    Returns:
        'essential', 'discretionary', or 'mixed'
    """
    if not category_name:
        return "discretionary"  # Default uncategorized to discretionary

    name_lower = category_name.lower().strip()

    # Check essential first (higher priority)
    for kw in ESSENTIAL_CATEGORIES:
        if kw in name_lower:
            return "essential"

    # Then check discretionary
    for kw in DISCRETIONARY_CATEGORIES:
        if kw in name_lower:
            return "discretionary"

    return "mixed"


def get_spending_breakdown(
    user_id: int,
    months: int = 3,
    month: str | None = None,
) -> dict[str, Any]:
    """
    Analyze essential vs discretionary spending for a user.

    Args:
        user_id: The user ID to analyze
        months: Number of months to include (if month not specified)
        month: Specific month in YYYY-MM format (overrides months param)

    Returns:
        Detailed breakdown with totals, percentages, categories, and insights
    """
    if month:
        # Parse specific month
        try:
            year, mo = int(month[:4]), int(month[5:7])
            start_date = date(year, mo, 1)
            if mo == 12:
                end_date = date(year + 1, 1, 1)
            else:
                end_date = date(year, mo + 1, 1)
        except (ValueError, IndexError):
            # Fallback to last 3 months
            end_date = date.today()
            start_date = end_date - timedelta(days=90)
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=30 * months)

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
            Expense.spent_at < end_date,
        )
        .all()
    )

    if not rows:
        return _empty_breakdown(months, month)

    total = float(sum(r.amount for r in rows))

    essential_total = 0.0
    discretionary_total = 0.0
    mixed_total = 0.0

    essential_by_cat: dict[str, float] = {}
    discretionary_by_cat: dict[str, float] = {}
    mixed_by_cat: dict[str, float] = {}

    for row in rows:
        amount = float(row.amount)
        cat = row.category_name or "Uncategorized"
        classification = _classify_category(cat)

        if classification == "essential":
            essential_total += amount
            essential_by_cat[cat] = essential_by_cat.get(cat, 0.0) + amount
        elif classification == "discretionary":
            discretionary_total += amount
            discretionary_by_cat[cat] = discretionary_by_cat.get(cat, 0.0) + amount
        else:
            mixed_total += amount
            mixed_by_cat[cat] = mixed_by_cat.get(cat, 0.0) + amount

    # For mixed, attempt to split based on ratio (50/50 by default)
    essential_total += mixed_total * 0.5
    discretionary_total += mixed_total * 0.5

    essential_pct = (essential_total / total * 100) if total > 0 else 0
    discretionary_pct = (discretionary_total / total * 100) if total > 0 else 0

    # Build insights
    insights = []
    if essential_pct > 70:
        insights.append({
            "type": "high_essential",
            "message": (
                f"Essential spending is {essential_pct:.1f}% of your budget. "
                "Limited discretionary room. Consider negotiating fixed costs like rent or insurance."
            ),
        })
    elif essential_pct < 40:
        insights.append({
            "type": "high_discretionary",
            "message": (
                f"Discretionary spending is {discretionary_pct:.1f}% of your total. "
                "You have good control over fixed costs. Review lifestyle choices for savings."
            ),
        })
    else:
        insights.append({
            "type": "balanced",
            "message": (
                f"Essential: {essential_pct:.1f}%, Discretionary: {discretionary_pct:.1f}%. "
                "Healthy spending balance. Target 50-60% essential for optimal savings."
            ),
        })

    # Top essential categories
    top_essential = sorted(essential_by_cat.items(), key=lambda x: x[1], reverse=True)[:5]
    top_discretionary = sorted(discretionary_by_cat.items(), key=lambda x: x[1], reverse=True)[:5]

    period_months = months if not month else 1

    return {
        "summary": {
            "total_spend": round(total, 2),
            "essential_total": round(essential_total, 2),
            "discretionary_total": round(discretionary_total, 2),
            "mixed_total": round(mixed_total, 2),
            "essential_pct": round(essential_pct, 1),
            "discretionary_pct": round(discretionary_pct, 1),
        },
        "essential": {
            "total": round(essential_total, 2),
            "percentage": round(essential_pct, 1),
            "categories": [
                {"name": cat, "amount": round(amt, 2), "pct": round(amt / total * 100, 1)}
                for cat, amt in top_essential
            ],
        },
        "discretionary": {
            "total": round(discretionary_total, 2),
            "percentage": round(discretionary_pct, 1),
            "categories": [
                {"name": cat, "amount": round(amt, 2), "pct": round(amt / total * 100, 1)}
                for cat, amt in top_discretionary
            ],
        },
        "mixed": {
            "total": round(mixed_total, 2),
            "categories": [
                {"name": cat, "amount": round(amt, 2)}
                for cat, amt in sorted(mixed_by_cat.items(), key=lambda x: x[1], reverse=True)[:3]
            ],
        },
        "insights": insights,
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "months": period_months,
            "specific_month": month,
        },
    }


def _empty_breakdown(months: int, month: str | None) -> dict[str, Any]:
    """Return empty breakdown structure when no data."""
    today = date.today()
    return {
        "summary": {
            "total_spend": 0.0,
            "essential_total": 0.0,
            "discretionary_total": 0.0,
            "mixed_total": 0.0,
            "essential_pct": 0.0,
            "discretionary_pct": 0.0,
        },
        "essential": {"total": 0.0, "percentage": 0.0, "categories": []},
        "discretionary": {"total": 0.0, "percentage": 0.0, "categories": []},
        "mixed": {"total": 0.0, "categories": []},
        "insights": [{"type": "no_data", "message": "No expense data found for this period."}],
        "period": {
            "start_date": (today - timedelta(days=30 * months)).isoformat(),
            "end_date": today.isoformat(),
            "months": months,
            "specific_month": month,
        },
    }
