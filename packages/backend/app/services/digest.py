"""Weekly financial digest service.

Generates smart weekly summaries highlighting spending trends, category
breakdowns, comparisons to previous weeks, and AI-powered insights.
"""

import json
from datetime import date, timedelta
from urllib import request as urllib_request

from sqlalchemy import func, and_

from ..config import Settings
from ..extensions import db
from ..models import Bill, Category, Expense

_settings = Settings()

DEFAULT_DIGEST_PERSONA = (
    "You are FinMind's weekly digest assistant. Analyze the user's weekly "
    "spending data and provide 2-3 concise, actionable insights. Be encouraging "
    "but honest about spending patterns. Focus on trends and specific suggestions."
)


def _get_week_bounds(week_start: date) -> tuple[date, date]:
    """Return (start, end) dates for a week starting on the given date."""
    # Ensure week_start is a Monday
    days_since_monday = week_start.weekday()
    start = week_start - timedelta(days=days_since_monday)
    end = start + timedelta(days=6)
    return start, end


def _get_current_week_start() -> date:
    """Return the Monday of the current week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def _weekly_totals(uid: int, week_start: date) -> tuple[float, float]:
    """Calculate total income and expenses for a given week."""
    start, end = _get_week_bounds(week_start)
    
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    return float(income or 0), float(expenses or 0)


def _weekly_category_breakdown(uid: int, week_start: date) -> list[dict]:
    """Get spending breakdown by category for a week."""
    start, end = _get_week_bounds(week_start)
    
    rows = (
        db.session.query(
            Expense.category_id,
            func.coalesce(Category.name, "Uncategorized").label("category_name"),
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("transaction_count"),
        )
        .outerjoin(
            Category,
            and_(Category.id == Expense.category_id, Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    
    total = sum(float(r.total_amount or 0) for r in rows)
    
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name,
            "amount": round(float(r.total_amount or 0), 2),
            "transaction_count": r.transaction_count,
            "share_pct": (
                round((float(r.total_amount or 0) / total) * 100, 2)
                if total > 0
                else 0
            ),
        }
        for r in rows
    ]


def _daily_breakdown(uid: int, week_start: date) -> list[dict]:
    """Get daily spending totals for a week."""
    start, end = _get_week_bounds(week_start)
    
    rows = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total_amount"),
            func.count(Expense.id).label("transaction_count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at.asc())
        .all()
    )
    
    # Create a dict for easy lookup
    daily_data = {r.spent_at: r for r in rows}
    
    # Build full week with zeros for missing days
    result = []
    current = start
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    while current <= end:
        data = daily_data.get(current)
        result.append({
            "date": current.isoformat(),
            "day_name": day_names[current.weekday()],
            "amount": round(float(data.total_amount), 2) if data else 0.0,
            "transaction_count": data.transaction_count if data else 0,
        })
        current += timedelta(days=1)
    
    return result


def _upcoming_bills_for_week(uid: int, week_start: date) -> list[dict]:
    """Get bills due within the specified week."""
    start, end = _get_week_bounds(week_start)
    
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start,
            Bill.next_due_date <= end,
        )
        .order_by(Bill.next_due_date.asc())
        .all()
    )
    
    return [
        {
            "id": b.id,
            "name": b.name,
            "amount": float(b.amount),
            "currency": b.currency,
            "next_due_date": b.next_due_date.isoformat(),
            "cadence": b.cadence.value,
            "autopay_enabled": b.autopay_enabled,
        }
        for b in bills
    ]


def _top_transactions(uid: int, week_start: date, limit: int = 5) -> list[dict]:
    """Get the largest transactions for the week."""
    start, end = _get_week_bounds(week_start)
    
    rows = (
        db.session.query(Expense)
        .outerjoin(
            Category,
            and_(Category.id == Expense.category_id, Category.user_id == uid),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start,
            Expense.spent_at <= end,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.amount.desc())
        .limit(limit)
        .all()
    )
    
    # Get category names
    category_ids = [e.category_id for e in rows if e.category_id]
    categories = {}
    if category_ids:
        cats = db.session.query(Category).filter(Category.id.in_(category_ids)).all()
        categories = {c.id: c.name for c in cats}
    
    return [
        {
            "id": e.id,
            "description": e.notes or "Transaction",
            "amount": float(e.amount),
            "date": e.spent_at.isoformat(),
            "category_name": categories.get(e.category_id, "Uncategorized"),
            "currency": e.currency,
        }
        for e in rows
    ]


def _calculate_trends(
    current_income: float,
    current_expenses: float,
    prev_income: float,
    prev_expenses: float,
) -> dict:
    """Calculate week-over-week trends."""
    expense_change = 0.0
    income_change = 0.0
    
    if prev_expenses > 0:
        expense_change = round(
            ((current_expenses - prev_expenses) / prev_expenses) * 100, 2
        )
    elif current_expenses > 0:
        expense_change = 100.0
    
    if prev_income > 0:
        income_change = round(
            ((current_income - prev_income) / prev_income) * 100, 2
        )
    elif current_income > 0:
        income_change = 100.0
    
    # Determine trend status
    if expense_change > 10:
        expense_trend = "increasing"
    elif expense_change < -10:
        expense_trend = "decreasing"
    else:
        expense_trend = "stable"
    
    return {
        "expense_change_pct": expense_change,
        "income_change_pct": income_change,
        "expense_trend": expense_trend,
        "previous_week_expenses": round(prev_expenses, 2),
        "previous_week_income": round(prev_income, 2),
    }


def _extract_json_object(raw: str) -> dict:
    """Extract JSON object from model response."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON object")
    return json.loads(text[start : end + 1])


def _generate_ai_insights(
    uid: int,
    week_start: date,
    summary: dict,
    category_breakdown: list,
    trends: dict,
    api_key: str,
    model: str,
    persona: str,
) -> dict:
    """Generate AI-powered insights using Gemini."""
    start, end = _get_week_bounds(week_start)
    
    prompt = (
        f"{persona}\n\n"
        "Analyze this weekly financial data and return strict JSON with keys:\n"
        "- insights: list of 2-3 short insight strings\n"
        "- highlight: one sentence summary of the week\n"
        "- suggestion: one actionable recommendation\n\n"
        f"Week: {start.isoformat()} to {end.isoformat()}\n"
        f"Total Income: {summary['total_income']}\n"
        f"Total Expenses: {summary['total_expenses']}\n"
        f"Net Flow: {summary['net_flow']}\n"
        f"Week-over-week expense change: {trends['expense_change_pct']}%\n"
        f"Top spending categories: {category_breakdown[:3]}\n"
    )
    
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
    ).encode("utf-8")
    
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    with urllib_request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    
    return _extract_json_object(text)


def _generate_heuristic_insights(
    summary: dict,
    category_breakdown: list,
    trends: dict,
    daily_breakdown: list,
) -> dict:
    """Generate insights using heuristics when AI is unavailable."""
    insights = []
    
    # Trend-based insight
    if trends["expense_change_pct"] > 20:
        insights.append(
            f"Spending increased {trends['expense_change_pct']}% compared to last week. "
            "Consider reviewing your discretionary expenses."
        )
    elif trends["expense_change_pct"] < -20:
        insights.append(
            f"Great job! You reduced spending by {abs(trends['expense_change_pct'])}% this week."
        )
    
    # Category-based insight
    if category_breakdown:
        top_cat = category_breakdown[0]
        insights.append(
            f"{top_cat['category_name']} was your biggest expense category at "
            f"{top_cat['share_pct']}% of total spending."
        )
    
    # Daily pattern insight
    if daily_breakdown:
        max_day = max(daily_breakdown, key=lambda x: x["amount"])
        if max_day["amount"] > 0:
            insights.append(
                f"Your highest spending day was {max_day['day_name']} "
                f"({max_day['date']}) at {max_day['amount']}."
            )
    
    # Net flow insight
    if summary["net_flow"] < 0:
        highlight = "You spent more than you earned this week."
        suggestion = "Try to identify non-essential expenses to cut back next week."
    elif summary["net_flow"] > 0:
        highlight = f"Positive cash flow of {summary['net_flow']} this week!"
        suggestion = "Consider putting the surplus towards savings or investments."
    else:
        highlight = "Your income matched your expenses this week."
        suggestion = "Look for small wins to build a positive buffer."
    
    return {
        "insights": insights[:3],
        "highlight": highlight,
        "suggestion": suggestion,
    }


def generate_weekly_digest(
    uid: int,
    week_start: date | None = None,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
) -> dict:
    """Generate a comprehensive weekly financial digest.
    
    Args:
        uid: User ID
        week_start: Start date of the week (defaults to current week's Monday)
        gemini_api_key: Optional Gemini API key for AI insights
        gemini_model: Optional Gemini model name
        persona: Optional AI persona for insights generation
    
    Returns:
        Dict containing weekly summary, trends, breakdowns, and insights
    """
    if week_start is None:
        week_start = _get_current_week_start()
    
    start, end = _get_week_bounds(week_start)
    prev_week_start = week_start - timedelta(days=7)
    
    # Calculate current and previous week totals
    current_income, current_expenses = _weekly_totals(uid, week_start)
    prev_income, prev_expenses = _weekly_totals(uid, prev_week_start)
    
    summary = {
        "total_income": round(current_income, 2),
        "total_expenses": round(current_expenses, 2),
        "net_flow": round(current_income - current_expenses, 2),
        "transaction_count": 0,  # Will be updated below
    }
    
    # Get breakdowns
    category_breakdown = _weekly_category_breakdown(uid, week_start)
    daily_breakdown = _daily_breakdown(uid, week_start)
    upcoming_bills = _upcoming_bills_for_week(uid, week_start)
    top_transactions = _top_transactions(uid, week_start)
    
    # Update transaction count from daily breakdown
    summary["transaction_count"] = sum(d["transaction_count"] for d in daily_breakdown)
    
    # Calculate trends
    trends = _calculate_trends(
        current_income, current_expenses, prev_income, prev_expenses
    )
    
    # Calculate bills total
    bills_total = sum(b["amount"] for b in upcoming_bills)
    
    # Generate insights
    api_key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_DIGEST_PERSONA).strip()
    
    ai_insights = None
    method = "heuristic"
    warnings = []
    
    if api_key:
        try:
            ai_insights = _generate_ai_insights(
                uid,
                week_start,
                summary,
                category_breakdown,
                trends,
                api_key,
                model,
                persona_text,
            )
            method = "gemini"
        except Exception:
            warnings.append("ai_insights_unavailable")
            ai_insights = _generate_heuristic_insights(
                summary, category_breakdown, trends, daily_breakdown
            )
    else:
        ai_insights = _generate_heuristic_insights(
            summary, category_breakdown, trends, daily_breakdown
        )
    
    result = {
        "period": {
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "week_number": start.isocalendar()[1],
            "year": start.year,
        },
        "summary": summary,
        "trends": trends,
        "category_breakdown": category_breakdown,
        "daily_breakdown": daily_breakdown,
        "upcoming_bills": {
            "items": upcoming_bills,
            "total": round(bills_total, 2),
            "count": len(upcoming_bills),
        },
        "top_transactions": top_transactions,
        "insights": ai_insights,
        "meta": {
            "method": method,
            "persona": persona_text,
        },
    }
    
    if warnings:
        result["warnings"] = warnings
    
    return result
