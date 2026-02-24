"""
spending_breakdown.py — Essential vs discretionary spending classification.

Classifies each expense category as ESSENTIAL or DISCRETIONARY using keyword
matching, with user-override support via CategoryClassification model.

Public API:
    classify_category(name, user_overrides) -> str
    get_spending_breakdown(uid, session, ym, reference_date) -> dict
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models import Category, CategoryClassification, Expense

logger = logging.getLogger("finmind.breakdown")

# ── Keyword classification rules ──────────────────────────────────────────────
_ESSENTIAL_KEYWORDS = {
    "rent", "mortgage", "housing", "utilities", "electric", "electricity",
    "water", "gas", "internet", "broadband", "phone", "mobile", "grocery",
    "groceries", "supermarket", "food", "transport", "commute", "fuel",
    "petrol", "diesel", "bus", "train", "metro", "healthcare", "medical",
    "doctor", "hospital", "pharmacy", "medicine", "insurance", "health",
    "education", "school", "tuition", "childcare", "tax", "emi", "loan",
}

_DISCRETIONARY_KEYWORDS = {
    "dining", "restaurant", "cafe", "coffee", "takeaway", "takeout",
    "entertainment", "movie", "cinema", "concert", "streaming", "netflix",
    "spotify", "amazon", "subscription", "shopping", "clothes", "fashion",
    "electronics", "gadget", "travel", "holiday", "vacation", "hotel",
    "flight", "uber", "ola", "cab", "taxi", "bar", "pub", "alcohol",
    "gym", "fitness", "beauty", "salon", "spa", "hobby", "game", "gaming",
    "gift", "donation", "luxury", "jewellery", "jewelry",
}


def classify_category(
    name: str,
    user_overrides: dict[int, str] | None = None,
    category_id: int | None = None,
) -> str:
    """
    Return "ESSENTIAL", "DISCRETIONARY", or "UNCATEGORISED" for a category name.

    user_overrides: {category_id: "ESSENTIAL"|"DISCRETIONARY"}
    """
    if user_overrides and category_id is not None:
        override = user_overrides.get(category_id)
        if override:
            return override

    words = set(name.lower().replace("-", " ").replace("_", " ").split())
    if words & _ESSENTIAL_KEYWORDS:
        return "ESSENTIAL"
    if words & _DISCRETIONARY_KEYWORDS:
        return "DISCRETIONARY"
    return "UNCATEGORISED"


def get_spending_breakdown(
    uid: int,
    session: Session,
    ym: str | None = None,
    reference_date: date | None = None,
) -> dict:
    """
    Return essential vs discretionary breakdown for a given month.

    Returns:
    {
      "month": "YYYY-MM",
      "total_spend": <float>,
      "essential": {
        "total": <float>,
        "pct_of_total_spend": <float>,
        "categories": [{"category_id", "category_name", "amount", "pct_of_type",
                         "pct_of_total", "classification", "user_override"}, ...]
      },
      "discretionary": { <same shape> },
      "uncategorised": { <same shape> },
      "insights": ["<str>", ...]
    }
    """
    ref = reference_date or date.today()
    if ym:
        try:
            year, month = map(int, ym.split("-"))
        except ValueError:
            year, month = ref.year, ref.month
    else:
        year, month = ref.year, ref.month

    month_str = f"{year}-{month:02d}"

    # Fetch user overrides
    overrides_rows = (
        session.query(CategoryClassification.category_id, CategoryClassification.classification)
        .filter_by(user_id=uid)
        .all()
    )
    overrides: dict[int, str] = {r.category_id: r.classification for r in overrides_rows}

    # Fetch category names
    cat_rows = session.query(Category.id, Category.name).filter_by(user_id=uid).all()
    cat_names: dict[int | None, str] = {r.id: r.name for r in cat_rows}
    cat_names[None] = "Uncategorised"

    # Fetch this month's spend per category
    rows = (
        session.query(Expense.category_id, func.sum(Expense.amount).label("total"))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )

    total_spend = sum(float(r.total) for r in rows)

    buckets: dict[str, list[dict]] = {
        "ESSENTIAL": [],
        "DISCRETIONARY": [],
        "UNCATEGORISED": [],
    }

    for r in rows:
        cat_id = r.category_id
        cat_name = cat_names.get(cat_id, f"Category {cat_id}")
        amount = float(r.total)
        cls = classify_category(cat_name, overrides, cat_id)
        buckets[cls].append({
            "category_id": cat_id,
            "category_name": cat_name,
            "amount": round(amount, 2),
            "pct_of_total": round(amount / total_spend * 100, 1) if total_spend else 0.0,
            "classification": cls,
            "user_override": cat_id in overrides,
        })

    def bucket_summary(items: list[dict]) -> dict:
        total = sum(i["amount"] for i in items)
        # sort by amount desc, compute pct_of_type
        for item in items:
            item["pct_of_type"] = round(item["amount"] / total * 100, 1) if total else 0.0
        items_sorted = sorted(items, key=lambda x: -x["amount"])
        return {
            "total": round(total, 2),
            "pct_of_total_spend": round(total / total_spend * 100, 1) if total_spend else 0.0,
            "categories": items_sorted,
        }

    essential     = bucket_summary(buckets["ESSENTIAL"])
    discretionary = bucket_summary(buckets["DISCRETIONARY"])
    uncategorised  = bucket_summary(buckets["UNCATEGORISED"])

    # Insights
    insights = []
    if total_spend == 0:
        insights.append(f"No spending recorded for {month_str}.")
    else:
        e_pct = essential["pct_of_total_spend"]
        d_pct = discretionary["pct_of_total_spend"]
        insights.append(
            f"Essential spending: {e_pct:.1f}% of total. "
            f"Discretionary: {d_pct:.1f}%."
        )
        if d_pct > 40:
            insights.append(
                f"Discretionary spending is high ({d_pct:.1f}%). "
                "Reviewing non-essential categories could free up budget."
            )
        if uncategorised["pct_of_total_spend"] > 20:
            insights.append(
                f"{uncategorised['pct_of_total_spend']:.1f}% of spend is uncategorised. "
                "Assigning categories will improve tracking accuracy."
            )

    logger.info(
        "Spending breakdown user=%s month=%s essential=%.1f%% discretionary=%.1f%%",
        uid, month_str, essential["pct_of_total_spend"], discretionary["pct_of_total_spend"],
    )

    return {
        "month": month_str,
        "total_spend": round(total_spend, 2),
        "essential": essential,
        "discretionary": discretionary,
        "uncategorised": uncategorised,
        "insights": insights,
    }
