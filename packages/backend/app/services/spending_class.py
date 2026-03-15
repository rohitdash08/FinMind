"""Essential vs discretionary spending classification.

Provides automatic and manual classification of spending categories
as essential or discretionary, with breakdown analysis and insights.
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func, and_

from ..extensions import db
from ..models import Category, Expense, SpendingClass

logger = logging.getLogger("finmind.spending_class")

# ─── Known category patterns for auto-classification ────────────────────

ESSENTIAL_PATTERNS = {
    "rent", "mortgage", "housing", "utilities", "electric", "electricity",
    "water", "gas", "internet", "phone", "mobile", "groceries", "grocery",
    "healthcare", "health", "medical", "medicine", "pharmacy", "insurance",
    "transport", "transportation", "fuel", "petrol", "commute", "transit",
    "childcare", "education", "tuition", "loan", "debt", "tax", "taxes",
    "savings", "emergency", "bills", "minimum payment",
}

DISCRETIONARY_PATTERNS = {
    "dining", "restaurant", "eating out", "takeout", "fast food",
    "entertainment", "movies", "cinema", "streaming", "gaming",
    "shopping", "clothing", "fashion", "accessories", "electronics",
    "travel", "vacation", "hotel", "flight", "airbnb",
    "subscription", "gym", "fitness", "spa", "beauty", "salon",
    "hobbies", "sports", "alcohol", "bar", "coffee", "cafe",
    "gifts", "donations", "luxury", "jewelry",
}


def classify_category(name: str) -> str:
    """Auto-classify a category name as essential or discretionary.

    Uses keyword matching against known patterns. Returns UNCLASSIFIED
    if no match is found.
    """
    lower = name.lower().strip()
    for pattern in ESSENTIAL_PATTERNS:
        if pattern in lower:
            return SpendingClass.ESSENTIAL.value
    for pattern in DISCRETIONARY_PATTERNS:
        if pattern in lower:
            return SpendingClass.DISCRETIONARY.value
    return SpendingClass.UNCLASSIFIED.value


def auto_classify_categories(user_id: int) -> dict:
    """Auto-classify all unclassified categories for a user.

    Returns summary of classifications made.
    """
    categories = (
        Category.query
        .filter_by(user_id=user_id, spending_class=SpendingClass.UNCLASSIFIED.value)
        .all()
    )

    classified = {"essential": 0, "discretionary": 0, "unclassified": 0}
    for cat in categories:
        new_class = classify_category(cat.name)
        cat.spending_class = new_class
        if new_class == SpendingClass.ESSENTIAL.value:
            classified["essential"] += 1
        elif new_class == SpendingClass.DISCRETIONARY.value:
            classified["discretionary"] += 1
        else:
            classified["unclassified"] += 1

    db.session.commit()
    logger.info(
        "Auto-classified categories for user=%d: %s", user_id, classified
    )
    return classified


def set_category_class(user_id: int, category_id: int, spending_class: str) -> dict | None:
    """Manually set the spending class for a category.

    Returns the updated category or None if not found.
    """
    cat = Category.query.filter_by(id=category_id, user_id=user_id).first()
    if not cat:
        return None

    cat.spending_class = spending_class
    db.session.commit()
    logger.info(
        "Set category %d to %s for user=%d", category_id, spending_class, user_id
    )
    return _cat_to_dict(cat)


def get_categories_by_class(user_id: int) -> dict:
    """Get all categories grouped by spending class."""
    categories = Category.query.filter_by(user_id=user_id).all()

    grouped = {
        "essential": [],
        "discretionary": [],
        "unclassified": [],
    }

    for cat in categories:
        key = cat.spending_class.lower() if cat.spending_class else "unclassified"
        if key not in grouped:
            key = "unclassified"
        grouped[key].append(_cat_to_dict(cat))

    return grouped


def get_spending_breakdown(
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict:
    """Get essential vs discretionary spending breakdown.

    Args:
        user_id: User ID.
        start_date: Start of period (default: 30 days ago).
        end_date: End of period (default: today).

    Returns:
        Breakdown with totals, percentages, and per-category details.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Get all expenses in period with category info
    expenses = (
        db.session.query(Expense, Category)
        .outerjoin(Category, Expense.category_id == Category.id)
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
        )
        .all()
    )

    essential_total = Decimal("0")
    discretionary_total = Decimal("0")
    unclassified_total = Decimal("0")
    grand_total = Decimal("0")

    category_totals = defaultdict(lambda: {
        "amount": Decimal("0"),
        "count": 0,
        "class": "UNCLASSIFIED",
        "name": "Uncategorized",
    })

    for expense, category in expenses:
        amount = expense.amount or Decimal("0")
        grand_total += amount

        if category:
            cat_key = category.id
            spending_class = category.spending_class or SpendingClass.UNCLASSIFIED.value
            category_totals[cat_key]["name"] = category.name
            category_totals[cat_key]["class"] = spending_class
        else:
            cat_key = 0
            spending_class = SpendingClass.UNCLASSIFIED.value
            category_totals[cat_key]["name"] = "Uncategorized"
            category_totals[cat_key]["class"] = spending_class

        category_totals[cat_key]["amount"] += amount
        category_totals[cat_key]["count"] += 1

        if spending_class == SpendingClass.ESSENTIAL.value:
            essential_total += amount
        elif spending_class == SpendingClass.DISCRETIONARY.value:
            discretionary_total += amount
        else:
            unclassified_total += amount

    # Build per-category breakdown
    essential_categories = []
    discretionary_categories = []
    unclassified_categories = []

    for cat_id, info in category_totals.items():
        entry = {
            "category_id": cat_id if cat_id != 0 else None,
            "name": info["name"],
            "amount": float(info["amount"]),
            "count": info["count"],
            "percentage": float(info["amount"] / grand_total * 100) if grand_total > 0 else 0,
        }
        if info["class"] == SpendingClass.ESSENTIAL.value:
            essential_categories.append(entry)
        elif info["class"] == SpendingClass.DISCRETIONARY.value:
            discretionary_categories.append(entry)
        else:
            unclassified_categories.append(entry)

    # Sort by amount descending
    essential_categories.sort(key=lambda x: x["amount"], reverse=True)
    discretionary_categories.sort(key=lambda x: x["amount"], reverse=True)
    unclassified_categories.sort(key=lambda x: x["amount"], reverse=True)

    return {
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
        },
        "totals": {
            "grand_total": float(grand_total),
            "essential": float(essential_total),
            "discretionary": float(discretionary_total),
            "unclassified": float(unclassified_total),
        },
        "percentages": {
            "essential": float(essential_total / grand_total * 100) if grand_total > 0 else 0,
            "discretionary": float(discretionary_total / grand_total * 100) if grand_total > 0 else 0,
            "unclassified": float(unclassified_total / grand_total * 100) if grand_total > 0 else 0,
        },
        "categories": {
            "essential": essential_categories,
            "discretionary": discretionary_categories,
            "unclassified": unclassified_categories,
        },
        "insights": _generate_insights(
            essential_total, discretionary_total, grand_total
        ),
    }


def get_spending_trend(
    user_id: int,
    months: int = 6,
) -> list[dict]:
    """Get monthly essential vs discretionary spending trend.

    Returns a list of monthly breakdowns for trend analysis.
    """
    today = date.today()
    trends = []

    for i in range(months - 1, -1, -1):
        # Calculate month boundaries
        month_start = date(today.year, today.month, 1) - timedelta(days=i * 30)
        month_start = date(month_start.year, month_start.month, 1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)

        breakdown = get_spending_breakdown(user_id, month_start, month_end)
        trends.append({
            "month": month_start.strftime("%Y-%m"),
            "essential": breakdown["totals"]["essential"],
            "discretionary": breakdown["totals"]["discretionary"],
            "unclassified": breakdown["totals"]["unclassified"],
            "total": breakdown["totals"]["grand_total"],
            "essential_pct": breakdown["percentages"]["essential"],
            "discretionary_pct": breakdown["percentages"]["discretionary"],
        })

    return trends


# ─── Internal helpers ────────────────────────────────────────────────────


def _cat_to_dict(cat: Category) -> dict:
    return {
        "id": cat.id,
        "name": cat.name,
        "spending_class": cat.spending_class,
        "created_at": cat.created_at.isoformat() if cat.created_at else None,
    }


def _generate_insights(
    essential: Decimal, discretionary: Decimal, total: Decimal,
) -> list[str]:
    """Generate spending insights based on the breakdown."""
    insights = []
    if total == 0:
        insights.append("No spending recorded in this period.")
        return insights

    ess_pct = float(essential / total * 100)
    disc_pct = float(discretionary / total * 100)

    if ess_pct > 70:
        insights.append(
            f"Essential spending is {ess_pct:.0f}% of total. "
            "Most of your budget goes to necessities."
        )
    elif ess_pct > 50:
        insights.append(
            f"Essential spending is {ess_pct:.0f}% of total. "
            "You have a healthy balance between needs and wants."
        )

    if disc_pct > 50:
        insights.append(
            f"Discretionary spending is {disc_pct:.0f}% of total. "
            "Consider reviewing non-essential expenses for savings opportunities."
        )
    elif disc_pct > 30:
        insights.append(
            f"Discretionary spending is {disc_pct:.0f}% of total. "
            "This is within a typical range."
        )
    elif disc_pct < 15 and total > 0:
        insights.append(
            f"Discretionary spending is only {disc_pct:.0f}% of total. "
            "You're being very frugal with non-essentials."
        )

    if float(essential) > 0 and float(discretionary) > 0:
        ratio = float(essential / discretionary)
        insights.append(
            f"Essential-to-discretionary ratio: {ratio:.1f}:1"
        )

    return insights
