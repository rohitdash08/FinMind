"""
Essential vs Discretionary Spending Breakdown — FinMind (#120)

Classifies user spending into essential (needs) and discretionary (wants)
categories, providing percentage breakdown and actionable insights.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.spending_breakdown")

# ── Classification rules ───────────────────────────────────────────────────────
# Keywords in category names (case-insensitive) that indicate essential spending
ESSENTIAL_KEYWORDS = frozenset([
    # Housing & utilities
    "rent", "mortgage", "housing", "utility", "utilities", "electric",
    "electricity", "water", "gas", "internet", "wifi", "phone", "mobile",
    "broadband", "maintenance", "repair", "repairs",
    # Food & groceries
    "grocery", "groceries", "supermarket", "food", "provisions",
    # Health & medical
    "health", "medical", "medicine", "pharmacy", "doctor", "hospital",
    "dental", "vision", "insurance", "prescription",
    # Transport & commute
    "transport", "transportation", "commute", "fuel", "petrol", "diesel",
    "bus", "train", "metro", "subway", "taxi", "uber", "ola", "auto",
    # Education
    "education", "school", "tuition", "fees", "books", "stationery",
    # Child & family care
    "childcare", "daycare", "baby", "infant",
    # EMI & loans
    "emi", "loan", "debt", "credit",
])

# Keywords indicating discretionary spending
DISCRETIONARY_KEYWORDS = frozenset([
    # Dining & entertainment
    "restaurant", "dining", "cafe", "coffee", "bar", "pub", "alcohol",
    "entertainment", "movie", "cinema", "theatre", "concert", "event",
    # Shopping & lifestyle
    "shopping", "fashion", "clothing", "clothes", "apparel", "accessories",
    "shoes", "jewellery", "jewelry",
    # Travel & leisure
    "travel", "vacation", "holiday", "hotel", "resort", "flight", "trip",
    "leisure", "tourism",
    # Beauty & personal care
    "beauty", "salon", "spa", "grooming", "cosmetics", "makeup",
    "personal care", "wellness",
    # Subscriptions & digital
    "subscription", "streaming", "netflix", "spotify", "amazon prime",
    "gaming", "game", "hobby", "sport", "gym", "fitness",
    # Gifts & misc
    "gift", "donation", "charity",
])


class CategoryBreakdown(TypedDict):
    category_id: int | None
    category_name: str
    classification: str   # "essential" | "discretionary" | "uncategorized"
    total_spent: float
    percentage_of_total: float
    transaction_count: int


class SpendingBreakdownResult(TypedDict):
    month: str
    total_spent: float
    essential_total: float
    discretionary_total: float
    uncategorized_total: float
    essential_percentage: float
    discretionary_percentage: float
    uncategorized_percentage: float
    categories: list[CategoryBreakdown]
    insight: str


# ── Internal helpers ───────────────────────────────────────────────────────────

def _classify_category(name: str | None) -> str:
    """Classify a category name as essential, discretionary, or uncategorized."""
    if not name:
        return "uncategorized"
    lower = name.lower().strip()
    # Check essential first
    for kw in ESSENTIAL_KEYWORDS:
        if kw in lower:
            return "essential"
    # Then discretionary
    for kw in DISCRETIONARY_KEYWORDS:
        if kw in lower:
            return "discretionary"
    return "uncategorized"


def _build_insight(essential_pct: float, discretionary_pct: float) -> str:
    """Generate a human-readable insight about the spending breakdown."""
    if essential_pct + discretionary_pct == 0:
        return "No categorized spending data available for this period."

    ratio = essential_pct / (essential_pct + discretionary_pct) if (essential_pct + discretionary_pct) > 0 else 0
    if ratio >= 0.80:
        return (
            f"Your spending is predominantly essential ({essential_pct:.0f}%). "
            f"You have limited discretionary flexibility this month."
        )
    elif ratio >= 0.60:
        return (
            f"You maintain a healthy balance: {essential_pct:.0f}% essential, "
            f"{discretionary_pct:.0f}% discretionary. "
            f"Consider reviewing discretionary items for savings opportunities."
        )
    elif ratio >= 0.40:
        return (
            f"Discretionary spending ({discretionary_pct:.0f}%) is high relative "
            f"to essential spending ({essential_pct:.0f}%). "
            f"Review non-essential expenses to improve savings."
        )
    else:
        return (
            f"Warning: discretionary spending ({discretionary_pct:.0f}%) significantly "
            f"exceeds essential spending ({essential_pct:.0f}%). "
            f"Consider reducing non-essential expenses."
        )


# ── Public API ─────────────────────────────────────────────────────────────────

def get_spending_breakdown(uid: int, ym: str) -> SpendingBreakdownResult:
    """Classify spending for user *uid* in month *ym* (YYYY-MM).

    Returns a full breakdown of essential vs discretionary spending with
    per-category classification and percentage insights.
    """
    year, month = int(ym[:4]), int(ym[5:7])

    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("cnt"),
        )
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .group_by(Expense.category_id, Category.name)
        .all()
    )

    if not rows:
        return SpendingBreakdownResult(
            month=ym,
            total_spent=0.0,
            essential_total=0.0,
            discretionary_total=0.0,
            uncategorized_total=0.0,
            essential_percentage=0.0,
            discretionary_percentage=0.0,
            uncategorized_percentage=0.0,
            categories=[],
            insight="No spending data available for this period.",
        )

    total = Decimal("0")
    essential = Decimal("0")
    discretionary = Decimal("0")
    uncategorized = Decimal("0")
    categories: list[CategoryBreakdown] = []

    # First pass: compute total
    for row in rows:
        total += Decimal(str(row.total))

    # Second pass: classify and build per-category breakdown
    for row in rows:
        cat_total = Decimal(str(row.total))
        classification = _classify_category(row.name)
        pct = float(cat_total / total * 100) if total > 0 else 0.0

        if classification == "essential":
            essential += cat_total
        elif classification == "discretionary":
            discretionary += cat_total
        else:
            uncategorized += cat_total

        categories.append(CategoryBreakdown(
            category_id=row.category_id,
            category_name=row.name or "Uncategorized",
            classification=classification,
            total_spent=round(float(cat_total), 2),
            percentage_of_total=round(pct, 1),
            transaction_count=row.cnt,
        ))

    # Sort categories: essential first, then discretionary, then uncategorized; by total desc
    cls_order = {"essential": 0, "discretionary": 1, "uncategorized": 2}
    categories.sort(key=lambda c: (cls_order.get(c["classification"], 3), -c["total_spent"]))

    total_f = round(float(total), 2)
    ess_f = round(float(essential), 2)
    disc_f = round(float(discretionary), 2)
    uncat_f = round(float(uncategorized), 2)
    ess_pct = round(float(essential / total * 100), 1) if total > 0 else 0.0
    disc_pct = round(float(discretionary / total * 100), 1) if total > 0 else 0.0
    uncat_pct = round(float(uncategorized / total * 100), 1) if total > 0 else 0.0

    logger.info(
        "spending_breakdown uid=%d month=%s total=%.2f ess=%.1f%% disc=%.1f%%",
        uid, ym, total_f, ess_pct, disc_pct,
    )

    return SpendingBreakdownResult(
        month=ym,
        total_spent=total_f,
        essential_total=ess_f,
        discretionary_total=disc_f,
        uncategorized_total=uncat_f,
        essential_percentage=ess_pct,
        discretionary_percentage=disc_pct,
        uncategorized_percentage=uncat_pct,
        categories=categories,
        insight=_build_insight(ess_pct, disc_pct),
    )