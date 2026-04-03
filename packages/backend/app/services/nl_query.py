import re
import json
from datetime import date, timedelta
from typing import Optional
from calendar import monthrange


# ─────────────────────────── Date parsing helpers ─────────────────────────────

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

_QUARTER_MAP = {"q1": (1, 3), "q2": (4, 6), "q3": (7, 9), "q4": (10, 12)}


def _current_quarter_range(today: date):
    quarter = (today.month - 1) // 3 + 1
    start_month, end_month = _QUARTER_MAP[f"q{quarter}"]
    start = date(today.year, start_month, 1)
    _, last_day = monthrange(today.year, end_month)
    end = date(today.year, end_month, last_day)
    return start, end


def _last_quarter_range(today: date):
    quarter = (today.month - 1) // 3 + 1
    prev_q = quarter - 1 if quarter > 1 else 4
    year = today.year if quarter > 1 else today.year - 1
    start_month, end_month = _QUARTER_MAP[f"q{prev_q}"]
    start = date(year, start_month, 1)
    _, last_day = monthrange(year, end_month)
    end = date(year, end_month, last_day)
    return start, end


def _specific_quarter_range(q_num: int, year: int):
    start_month, end_month = _QUARTER_MAP[f"q{q_num}"]
    start = date(year, start_month, 1)
    _, last_day = monthrange(year, end_month)
    end = date(year, end_month, last_day)
    return start, end


def _this_month_range(today: date):
    start = date(today.year, today.month, 1)
    _, last_day = monthrange(today.year, today.month)
    end = date(today.year, today.month, last_day)
    return start, end


def _last_month_range(today: date):
    first_of_this = date(today.year, today.month, 1)
    last_of_prev = first_of_this - timedelta(days=1)
    start = date(last_of_prev.year, last_of_prev.month, 1)
    return start, last_of_prev


def _this_year_range(today: date):
    return date(today.year, 1, 1), date(today.year, 12, 31)


def _last_n_days(n: int, today: date):
    return today - timedelta(days=n - 1), today


def parse_date_range(query: str, today: Optional[date] = None) -> tuple[date, date]:
    """Extract a (start, end) date range from a natural language query."""
    today = today or date.today()
    q = query.lower()

    # "last N days"
    m = re.search(r"last\s+(\d+)\s+days?", q)
    if m:
        return _last_n_days(int(m.group(1)), today)

    # "last N weeks"
    m = re.search(r"last\s+(\d+)\s+weeks?", q)
    if m:
        days = int(m.group(1)) * 7
        return _last_n_days(days, today)

    # "last N months"
    m = re.search(r"last\s+(\d+)\s+months?", q)
    if m:
        months = int(m.group(1))
        start = date(today.year - (months // 12), today.month - (months % 12) or 12, 1)
        # simple approximation
        start = today.replace(day=1) - timedelta(days=months * 30)
        start = date(start.year, start.month, 1)
        return start, today

    # "Q1 2025" / "Q2 last year"
    m = re.search(r"q([1-4])\s+(\d{4})", q)
    if m:
        return _specific_quarter_range(int(m.group(1)), int(m.group(2)))

    # "last quarter"
    if "last quarter" in q:
        return _last_quarter_range(today)

    # "this quarter"
    if "this quarter" in q or "current quarter" in q:
        return _current_quarter_range(today)

    # "last month"
    if "last month" in q:
        return _last_month_range(today)

    # "this month" / "current month"
    if "this month" in q or "current month" in q:
        return _this_month_range(today)

    # "this year"
    if "this year" in q or "current year" in q:
        return _this_year_range(today)

    # "last year"
    if "last year" in q:
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)

    # Specific month name "in april" / "in april 2024"
    for month_name, month_num in _MONTHS.items():
        pattern = rf"\bin\s+{month_name}(?:\s+(\d{{4}}))?(?:\b|$)"
        m = re.search(pattern, q)
        if m:
            year = int(m.group(1)) if m.group(1) else today.year
            _, last_day = monthrange(year, month_num)
            return date(year, month_num, 1), date(year, month_num, last_day)

    # Default: last 30 days
    return _last_n_days(30, today)


# ─────────────────────────── Category extraction ─────────────────────────────

_CATEGORY_KEYWORDS = {
    "food": ["food", "eat", "restaurant", "lunch", "dinner", "breakfast", "groceries", "grocery", "meal", "coffee", "cafe"],
    "transport": ["transport", "travel", "uber", "cab", "taxi", "fuel", "petrol", "gas", "commute", "bus", "train", "metro", "flight"],
    "entertainment": ["entertainment", "movie", "netflix", "spotify", "gaming", "game", "subscription", "concert", "sport"],
    "health": ["health", "medical", "pharmacy", "doctor", "gym", "fitness", "medicine", "hospital"],
    "shopping": ["shopping", "clothes", "clothing", "amazon", "purchase", "buy", "bought", "store"],
    "bills": ["bill", "bills", "utility", "utilities", "electricity", "water", "internet", "rent"],
    "education": ["education", "course", "book", "tuition", "school", "college", "university", "learning"],
}


def extract_category(query: str) -> Optional[str]:
    """Extract the most likely spending category from a natural language query."""
    q = query.lower()
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return category
    return None


# ─────────────────────────── Main query executor ─────────────────────────────

def execute_nl_query(query: str, user_id: int, today: Optional[date] = None):
    """
    Execute a natural language finance query and return structured results.
    Returns a dict with: query, start_date, end_date, category, total, transaction_count, transactions.
    """
    from ..models import Expense
    from ..extensions import db
    from sqlalchemy import func

    today = today or date.today()
    start_date, end_date = parse_date_range(query, today)
    category_hint = extract_category(query)

    # Build base query
    expense_query = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.spent_at >= start_date,
        Expense.spent_at <= end_date,
    )

    # Apply category filter if we found a category keyword
    if category_hint:
        from ..models import Category
        category_objs = Category.query.filter(
            Category.user_id == user_id,
            Category.name.ilike(f"%{category_hint}%"),
        ).all()
        if category_objs:
            cat_ids = [c.id for c in category_objs]
            expense_query = expense_query.filter(Expense.category_id.in_(cat_ids))

    expenses = expense_query.order_by(Expense.spent_at.desc()).limit(50).all()
    total = sum(float(e.amount) for e in expenses)

    return {
        "query": query,
        "interpreted": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "category": category_hint,
        },
        "total": round(total, 2),
        "transaction_count": len(expenses),
        "transactions": [
            {
                "id": e.id,
                "amount": float(e.amount),
                "currency": e.currency,
                "notes": e.notes,
                "spent_at": e.spent_at.isoformat(),
                "category_id": e.category_id,
            }
            for e in expenses
        ],
    }
