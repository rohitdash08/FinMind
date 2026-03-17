"""
Natural Language Finance Query (Issue #74).

Parses natural language questions about personal finances and returns
accurate answers backed by real DB data.

No external ML/NLP dependencies — uses a deterministic rule-based parser
that covers the most common query patterns:

Query patterns supported
------------------------
- "how much did I spend on [category] [date range]?"
- "what did I spend on [category] last [month/week/quarter/year]?"
- "how much did I earn/receive [date range]?"
- "what is my total expenses for [date range]?"
- "how many transactions [date range]?"
- "what is my net flow for [month/period]?"
- "show my top categories [date range]?"
- "what is my average spending [date range]?"

Date range keywords
-------------------
last week, last month, last quarter, last year,
this month, this week, this year,
in [month name], in [YYYY], in [YYYY-MM]
"""

from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.nl_query")

# ── Date range parsing ────────────────────────────────────────────────────────

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _parse_date_range(text: str, anchor: date) -> tuple[date, date, str]:
    """
    Extract a date range from *text*.
    Returns (start_date, end_date, human_label).
    Defaults to current month if no date keyword found.
    """
    t = text.lower()

    # last N days
    m = re.search(r"last (\d+) days?", t)
    if m:
        n = int(m.group(1))
        return anchor - timedelta(days=n), anchor, f"last {n} days"

    if "last week" in t:
        start = anchor - timedelta(days=anchor.weekday() + 7)
        end   = start + timedelta(days=6)
        return start, end, "last week"

    if "last quarter" in t:
        q = (anchor.month - 1) // 3
        if q == 0:
            start = date(anchor.year - 1, 10, 1)
            end   = date(anchor.year - 1, 12, 31)
        else:
            start = date(anchor.year, (q - 1) * 3 + 1, 1)
            end   = date(anchor.year, q * 3, 1) - timedelta(days=1)
        return start, end, "last quarter"

    if "last year" in t:
        y = anchor.year - 1
        return date(y, 1, 1), date(y, 12, 31), f"last year ({y})"

    if "last month" in t:
        if anchor.month == 1:
            start = date(anchor.year - 1, 12, 1)
            end   = date(anchor.year - 1, 12, 31)
        else:
            start = date(anchor.year, anchor.month - 1, 1)
            end   = date(anchor.year, anchor.month, 1) - timedelta(days=1)
        return start, end, f"last month ({start.strftime('%B %Y')})"

    if "this week" in t:
        start = anchor - timedelta(days=anchor.weekday())
        end   = start + timedelta(days=6)
        return start, end, "this week"

    if "this year" in t:
        return date(anchor.year, 1, 1), anchor, f"this year ({anchor.year})"

    if "this month" in t or "current month" in t:
        return date(anchor.year, anchor.month, 1), anchor, f"this month ({anchor.strftime('%B %Y')})"

    # "in YYYY-MM"
    m = re.search(r"\bin (\d{4})-(\d{2})\b", t)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        start = date(y, mo, 1)
        end   = date(y, mo + 1, 1) - timedelta(days=1) if mo < 12 else date(y, 12, 31)
        return start, end, f"{start.strftime('%B %Y')}"

    # "in YYYY"
    m = re.search(r"\bin (\d{4})\b", t)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31), str(y)

    # "in [month name]" or "last [month name]"
    for name, mo in _MONTH_NAMES.items():
        if re.search(rf"\b(?:in |last )?{name}\b", t):
            y = anchor.year if mo <= anchor.month else anchor.year - 1
            start = date(y, mo, 1)
            end   = date(y, mo + 1, 1) - timedelta(days=1) if mo < 12 else date(y, 12, 31)
            return start, end, start.strftime("%B %Y")

    # Default: current month
    return date(anchor.year, anchor.month, 1), anchor, f"this month ({anchor.strftime('%B %Y')})"


# ── Category matching ─────────────────────────────────────────────────────────

def _find_category(uid: int, text: str) -> tuple[int | None, str | None]:
    """Try to match a category name in *text*. Returns (cat_id, cat_name) or (None, None)."""
    cats = db.session.query(Category).filter_by(user_id=uid).all()
    t = text.lower()
    for cat in cats:
        if cat.name.lower() in t:
            return cat.id, cat.name
    return None, None


# ── Query execution ───────────────────────────────────────────────────────────

def _sum_expenses(uid: int, start: date, end: date, cat_id: int | None = None) -> float:
    q = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "EXPENSE",
        )
    )
    if cat_id is not None:
        q = q.filter(Expense.category_id == cat_id)
    return float(q.scalar() or 0)


def _sum_income(uid: int, start: date, end: date) -> float:
    return float(
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar() or 0
    )


def _count_transactions(uid: int, start: date, end: date) -> int:
    return int(
        db.session.query(func.count(Expense.id))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
        )
        .scalar() or 0
    )


def _top_categories(uid: int, start: date, end: date, limit: int = 5) -> list[dict]:
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "EXPENSE",
        )
        .group_by(Expense.category_id)
        .order_by(func.sum(Expense.amount).desc())
        .limit(limit)
        .all()
    )
    result = []
    for r in rows:
        cat = db.session.get(Category, r.category_id) if r.category_id else None
        result.append({
            "category": cat.name if cat else "Uncategorized",
            "amount": float(r.total),
        })
    return result


# ── Intent detection ──────────────────────────────────────────────────────────

def _detect_intent(text: str) -> str:
    t = text.lower()
    if re.search(r"\b(earn|income|receive|received|salary|got paid)\b", t):
        return "income"
    if re.search(r"\b(net|flow|save|saved|balance)\b", t):
        return "net_flow"
    if re.search(r"\b(how many|count|number of|transactions?)\b", t):
        return "count"
    if re.search(r"\b(top|biggest|most|largest|highest)\b", t):
        return "top_categories"
    if re.search(r"\b(average|avg|mean|typical)\b", t):
        return "average"
    return "spend"   # default


# ── Public API ────────────────────────────────────────────────────────────────

def answer_query(uid: int, query: str, anchor: date | None = None) -> dict[str, Any]:
    """
    Parse and answer a natural language finance query.

    Returns:
        query         — original query text
        intent        — detected intent
        date_range    — {start, end, label}
        category      — matched category name (or null)
        answer        — scalar answer (amount, count, etc.)
        answer_text   — human-readable sentence
        source_data   — supporting data (top categories, etc.)
        confidence    — 'high' | 'medium' | 'low'
    """
    if anchor is None:
        anchor = date.today()

    query_clean = query.strip()
    start, end, date_label = _parse_date_range(query_clean, anchor)
    intent = _detect_intent(query_clean)
    cat_id, cat_name = _find_category(uid, query_clean)

    source: dict[str, Any] = {}
    answer: float | int = 0
    answer_text = ""
    confidence = "high"

    if intent == "spend":
        total = _sum_expenses(uid, start, end, cat_id)
        answer = round(total, 2)
        if cat_name:
            answer_text = f"You spent {total:,.2f} on {cat_name} {date_label}."
        else:
            answer_text = f"Your total expenses for {date_label} were {total:,.2f}."
        source = {"total_expenses": answer, "category": cat_name}

    elif intent == "income":
        total = _sum_income(uid, start, end)
        answer = round(total, 2)
        answer_text = f"Your total income for {date_label} was {total:,.2f}."
        source = {"total_income": answer}

    elif intent == "net_flow":
        income   = _sum_income(uid, start, end)
        expenses = _sum_expenses(uid, start, end)
        net = round(income - expenses, 2)
        answer = net
        direction = "saved" if net >= 0 else "overspent by"
        answer_text = f"For {date_label}, you {direction} {abs(net):,.2f} (income: {income:,.2f}, expenses: {expenses:,.2f})."
        source = {"income": round(income, 2), "expenses": round(expenses, 2), "net": net}

    elif intent == "count":
        count = _count_transactions(uid, start, end)
        answer = count
        answer_text = f"You had {count} transactions {date_label}."
        source = {"transaction_count": count}

    elif intent == "top_categories":
        tops = _top_categories(uid, start, end)
        answer = len(tops)
        if tops:
            top_str = ", ".join(f"{t['category']} ({t['amount']:,.2f})" for t in tops[:3])
            answer_text = f"Your top spending categories for {date_label}: {top_str}."
        else:
            answer_text = f"No spending data found for {date_label}."
        source = {"top_categories": tops}

    elif intent == "average":
        total  = _sum_expenses(uid, start, end, cat_id)
        # Count days in range
        days   = max(1, (end - start).days + 1)
        months = max(1, days // 30)
        avg    = round(total / months, 2)
        answer = avg
        label  = cat_name or "total"
        answer_text = f"Your average monthly {label} spending for {date_label} was {avg:,.2f}."
        source = {"total": round(total, 2), "months": months, "avg_monthly": avg}

    # Confidence based on whether date range was explicitly mentioned
    t_lower = query_clean.lower()
    if not any(kw in t_lower for kw in ["last", "this", "month", "week", "year", "quarter", "in "]):
        confidence = "medium"  # date range defaulted

    logger.info("NL query uid=%s intent=%s cat=%s date=%s→%s answer=%s",
                uid, intent, cat_name, start, end, answer)

    return {
        "query":      query_clean,
        "intent":     intent,
        "date_range": {"start": start.isoformat(), "end": end.isoformat(), "label": date_label},
        "category":   cat_name,
        "answer":     answer,
        "answer_text": answer_text,
        "source_data": source,
        "confidence": confidence,
    }
