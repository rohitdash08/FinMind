"""Essential vs discretionary spending breakdown."""

from datetime import date, timedelta
from decimal import Decimal

from ..extensions import db
from ..models import Expense, Category
import logging

logger = logging.getLogger("finmind.spending")

# Default classification of categories
ESSENTIAL_KEYWORDS = [
    "rent", "mortgage", "housing", "utilities", "electricity", "water", "gas",
    "internet", "phone", "groceries", "food", "transport", "fuel", "insurance",
    "medical", "health", "pharmacy", "education", "childcare",
]

DISCRETIONARY_KEYWORDS = [
    "entertainment", "dining", "restaurant", "cafe", "shopping", "clothing",
    "subscription", "netflix", "spotify", "gym", "travel", "vacation",
    "hobby", "gaming", "alcohol", "bar",
]


def classify_category(category_name: str) -> str:
    """Classify a category as essential or discretionary."""
    name_lower = category_name.lower()
    for kw in ESSENTIAL_KEYWORDS:
        if kw in name_lower:
            return "essential"
    for kw in DISCRETIONARY_KEYWORDS:
        if kw in name_lower:
            return "discretionary"
    return "uncategorized"


def spending_breakdown(user_id: int, days: int = 30) -> dict:
    """Break down spending into essential vs discretionary.

    Returns totals, percentages, and per-category breakdown.
    """
    cutoff = date.today() - timedelta(days=days)

    expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.spent_at >= cutoff,
            Expense.expense_type == "EXPENSE",
        )
        .all()
    )

    categories = {
        c.id: c.name
        for c in db.session.query(Category).filter_by(user_id=user_id).all()
    }

    essential_total = Decimal("0")
    discretionary_total = Decimal("0")
    uncategorized_total = Decimal("0")
    by_category = []

    cat_totals: dict[int, Decimal] = {}
    for e in expenses:
        cat_id = e.category_id or 0
        cat_totals.setdefault(cat_id, Decimal("0"))
        cat_totals[cat_id] += Decimal(str(e.amount))

    for cat_id, total in cat_totals.items():
        cat_name = categories.get(cat_id, "Uncategorized")
        classification = classify_category(cat_name)

        if classification == "essential":
            essential_total += total
        elif classification == "discretionary":
            discretionary_total += total
        else:
            uncategorized_total += total

        by_category.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "amount": float(total),
            "classification": classification,
        })

    grand_total = essential_total + discretionary_total + uncategorized_total

    return {
        "period_days": days,
        "total_spending": float(grand_total),
        "essential": {
            "total": float(essential_total),
            "percent": round(float(essential_total / grand_total * 100), 1) if grand_total else 0,
        },
        "discretionary": {
            "total": float(discretionary_total),
            "percent": round(float(discretionary_total / grand_total * 100), 1) if grand_total else 0,
        },
        "uncategorized": {
            "total": float(uncategorized_total),
            "percent": round(float(uncategorized_total / grand_total * 100), 1) if grand_total else 0,
        },
        "by_category": sorted(by_category, key=lambda c: -c["amount"]),
    }
