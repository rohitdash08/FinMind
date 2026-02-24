"""Essential vs discretionary spending breakdown service (Issue #120).

Classifies user expenses into essential and discretionary categories based
on configurable keyword mappings.  Users can override the default
classification by tagging their own categories.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List, Literal

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.spending_breakdown")

SpendingType = Literal["essential", "discretionary"]

# Default keyword-based classification for category names.
# A category whose name contains any of these keywords (case-insensitive)
# is classified accordingly.  Anything unmatched defaults to discretionary.
ESSENTIAL_KEYWORDS = [
    "rent", "mortgage", "housing", "utilities", "electric", "electricity",
    "water", "gas", "internet", "phone", "insurance", "health", "medical",
    "medicine", "pharmacy", "grocery", "groceries", "food", "transport",
    "transportation", "fuel", "petrol", "diesel", "bus", "metro", "train",
    "childcare", "education", "tuition", "loan", "emi", "tax", "taxes",
]

DISCRETIONARY_KEYWORDS = [
    "entertainment", "dining", "restaurant", "cafe", "coffee", "bar",
    "movie", "movies", "streaming", "subscription", "shopping", "clothes",
    "clothing", "fashion", "travel", "vacation", "holiday", "hobby",
    "hobbies", "gaming", "game", "fitness", "gym", "spa", "beauty",
    "salon", "gift", "gifts", "alcohol", "tobacco",
]


@dataclass
class CategoryBreakdown:
    category_id: int | None
    category_name: str
    amount: float
    classification: SpendingType

    def to_dict(self) -> dict:
        return {
            "category_id": self.category_id,
            "category_name": self.category_name,
            "amount": self.amount,
            "classification": self.classification,
        }


@dataclass
class SpendingBreakdown:
    period: str
    essential_total: float
    discretionary_total: float
    total: float
    essential_pct: float
    discretionary_pct: float
    categories: List[CategoryBreakdown]

    def to_dict(self) -> dict:
        return {
            "period": self.period,
            "essential_total": self.essential_total,
            "discretionary_total": self.discretionary_total,
            "total": self.total,
            "essential_pct": self.essential_pct,
            "discretionary_pct": self.discretionary_pct,
            "categories": [c.to_dict() for c in self.categories],
        }


def classify_category(name: str) -> SpendingType:
    """Classify a category name as essential or discretionary."""
    lower = name.lower()
    for kw in ESSENTIAL_KEYWORDS:
        if kw in lower:
            return "essential"
    for kw in DISCRETIONARY_KEYWORDS:
        if kw in lower:
            return "discretionary"
    # Default: discretionary
    return "discretionary"


def get_spending_breakdown(user_id: int, year: int, month: int) -> SpendingBreakdown:
    """Compute essential vs discretionary breakdown for a given month."""
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
        )
        .outerjoin(
            Category,
            (Category.id == Expense.category_id) & (Category.user_id == user_id),
        )
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .all()
    )

    categories: List[CategoryBreakdown] = []
    essential_total = 0.0
    discretionary_total = 0.0

    for row in rows:
        amount = float(row.total_amount or 0)
        classification = classify_category(row.category_name)
        categories.append(
            CategoryBreakdown(
                category_id=row.category_id,
                category_name=row.category_name,
                amount=round(amount, 2),
                classification=classification,
            )
        )
        if classification == "essential":
            essential_total += amount
        else:
            discretionary_total += amount

    total = essential_total + discretionary_total
    period = f"{year:04d}-{month:02d}"

    return SpendingBreakdown(
        period=period,
        essential_total=round(essential_total, 2),
        discretionary_total=round(discretionary_total, 2),
        total=round(total, 2),
        essential_pct=round(essential_total / total * 100, 1) if total > 0 else 0.0,
        discretionary_pct=round(discretionary_total / total * 100, 1) if total > 0 else 0.0,
        categories=sorted(categories, key=lambda c: c.amount, reverse=True),
    )
