"""
Weekly digest service for generating financial summaries and insights.
"""
import json
from datetime import datetime, timedelta, date
from urllib import request
from sqlalchemy import extract, func, and_

from ..config import Settings
from ..extensions import db
from ..models import Expense, Bill, Category

_settings = Settings()


def _parse_week_param(week_str: str) -> tuple[int, int]:
    """
    Parse week parameter in format YYYY-WNN (e.g., 2026-W08).
    Returns (year, week_number).
    """
    if not week_str or len(week_str) != 8 or week_str[4] != "-" or week_str[5] != "W":
        raise ValueError("Invalid week format. Expected YYYY-WNN")
    
    year = int(week_str[:4])
    week = int(week_str[6:])
    
    if not (1 <= week <= 53):
        raise ValueError("Week number must be between 1 and 53")
    
    return year, week


def _get_week_date_range(year: int, week: int) -> tuple[date, date]:
    """
    Get start and end dates for a given ISO week.
    Returns (start_date, end_date) where start is Monday and end is Sunday.
    """
    # ISO week date calculation
    jan_4 = date(year, 1, 4)
    week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
    start_date = week_1_monday + timedelta(weeks=week - 1)
    end_date = start_date + timedelta(days=6)
    
    return start_date, end_date


def _get_week_expenses(uid: int, start_date: date, end_date: date) -> dict:
    """
    Get expense data for a specific week.
    """
    # Total income and expenses
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    # Category breakdown
    category_rows = (
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
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name)
        .order_by(func.sum(Expense.amount).desc())
        .all()
    )
    
    # Daily spending pattern
    daily_spending = (
        db.session.query(
            Expense.spent_at,
            func.coalesce(func.sum(Expense.amount), 0).label("total"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_date,
            Expense.spent_at <= end_date,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.spent_at)
        .order_by(Expense.spent_at)
        .all()
    )
    
    return {
        "total_income": float(income or 0),
        "total_expenses": float(expenses or 0),
        "net_flow": float((income or 0) - (expenses or 0)),
        "categories": [
            {
                "category_id": r.category_id,
                "category_name": r.category_name,
                "amount": float(r.total_amount or 0),
                "transaction_count": r.transaction_count,
            }
            for r in category_rows
        ],
        "daily_spending": [
            {
                "date": d.spent_at.isoformat(),
                "amount": float(d.total or 0),
            }
            for d in daily_spending
        ],
    }


def _get_week_bills(uid: int, start_date: date, end_date: date) -> dict:
    """
    Get bills due during the week.
    """
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active.is_(True),
            Bill.next_due_date >= start_date,
            Bill.next_due_date <= end_date,
        )
        .order_by(Bill.next_due_date)
        .all()
    )
    
    return {
        "count": len(bills),
        "total_amount": sum(float(b.amount) for b in bills),
        "bills": [
            {
                "id": b.id,
                "name": b.name,
                "amount": float(b.amount),
                "due_date": b.next_due_date.isoformat(),
                "cadence": b.cadence.value,
            }
            for b in bills
        ],
    }


def _compare_with_previous_week(
    uid: int, current_start: date, current_end: date
) -> dict:
    """
    Compare current week with previous week.
    """
    prev_start = current_start - timedelta(days=7)
    prev_end = current_end - timedelta(days=7)
    
    current_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= current_start,
            Expense.spent_at <= current_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    prev_expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= prev_start,
            Expense.spent_at <= prev_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    
    current = float(current_expenses or 0)
    previous = float(prev_expenses or 0)
    
    if previous > 0:
        change_pct = round(((current - previous) / previous) * 100, 2)
    else:
        change_pct = 0.0
    
    return {
        "current_week_expenses": round(current, 2),
        "previous_week_expenses": round(previous, 2),
        "change_amount": round(current - previous, 2),
        "change_percentage": change_pct,
    }


def _generate_insights(data: dict, gemini_api_key: str | None = None) -> list[str]:
    """
    Generate AI-powered insights from weekly data.
    Falls back to heuristic insights if Gemini is unavailable.
    """
    if gemini_api_key:
        try:
            return _gemini_insights(data, gemini_api_key)
        except Exception:
            pass  # Fall back to heuristic
    
    return _heuristic_insights(data)


def _heuristic_insights(data: dict) -> list[str]:
    """
    Generate rule-based insights from weekly data.
    """
    insights = []
    
    # Net flow insight
    net_flow = data["expenses"]["net_flow"]
    if net_flow > 0:
        insights.append(
            f"Great job! You saved {abs(net_flow):.2f} this week. "
            "Keep up the positive cash flow!"
        )
    elif net_flow < 0:
        insights.append(
            f"You spent {abs(net_flow):.2f} more than you earned this week. "
            "Consider reviewing your expenses."
        )
    
    # Week-over-week comparison
    comparison = data["comparison"]
    if comparison["change_percentage"] > 20:
        insights.append(
            f"Your spending increased by {comparison['change_percentage']}% "
            f"compared to last week. Review your top categories."
        )
    elif comparison["change_percentage"] < -20:
        insights.append(
            f"Excellent! You reduced spending by {abs(comparison['change_percentage'])}% "
            f"compared to last week."
        )
    
    # Top category insight
    categories = data["expenses"]["categories"]
    if categories:
        top_cat = categories[0]
        total_expenses = data["expenses"]["total_expenses"]
        if total_expenses > 0:
            pct = (top_cat["amount"] / total_expenses) * 100
            if pct > 40:
                insights.append(
                    f"{top_cat['category_name']} accounts for {pct:.1f}% of your "
                    f"weekly spending. Consider if this aligns with your priorities."
                )
    
    # Bills insight
    if data["bills"]["count"] > 0:
        insights.append(
            f"You have {data['bills']['count']} bill(s) due this week "
            f"totaling {data['bills']['total_amount']:.2f}. Don't forget to pay them!"
        )
    
    # Daily spending pattern
    daily = data["expenses"]["daily_spending"]
    if len(daily) >= 3:
        amounts = [d["amount"] for d in daily]
        avg = sum(amounts) / len(amounts)
        max_day = max(daily, key=lambda x: x["amount"])
        if max_day["amount"] > avg * 2:
            insights.append(
                f"Your highest spending day was {max_day['date']} "
                f"with {max_day['amount']:.2f}. Try to spread expenses more evenly."
            )
    
    return insights[:5]  # Return top 5 insights


def _gemini_insights(data: dict, api_key: str) -> list[str]:
    """
    Generate AI-powered insights using Gemini.
    """
    prompt = (
        "You are a financial advisor analyzing weekly spending data. "
        "Provide 3-5 concise, actionable insights based on this data. "
        "Return ONLY a JSON array of strings, no other text.\\n\\n"
        f"Data: {json.dumps(data, indent=2)}"
    )
    
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{_settings.gemini_model}:generateContent?key={api_key}"
    )
    
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3},
        }
    ).encode("utf-8")
    
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    
    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    
    # Extract JSON array from response
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        insights = json.loads(text[start : end + 1])
        return insights if isinstance(insights, list) else []
    
    raise ValueError("Could not parse insights from Gemini response")


def generate_weekly_digest(
    uid: int,
    week: str,
    gemini_api_key: str | None = None,
) -> dict:
    """
    Generate a comprehensive weekly financial digest.
    
    Args:
        uid: User ID
        week: Week in format YYYY-WNN (e.g., "2026-W08")
        gemini_api_key: Optional Gemini API key for AI insights
    
    Returns:
        Dictionary containing weekly summary, trends, and insights
    """
    year, week_num = _parse_week_param(week)
    start_date, end_date = _get_week_date_range(year, week_num)
    
    # Gather all data
    expenses_data = _get_week_expenses(uid, start_date, end_date)
    bills_data = _get_week_bills(uid, start_date, end_date)
    comparison_data = _compare_with_previous_week(uid, start_date, end_date)
    
    # Build complete data structure
    digest_data = {
        "period": {
            "week": week,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "expenses": expenses_data,
        "bills": bills_data,
        "comparison": comparison_data,
    }
    
    # Generate insights
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    insights = _generate_insights(digest_data, key if key else None)
    digest_data["insights"] = insights
    
    # Add metadata
    digest_data["generated_at"] = datetime.utcnow().isoformat()
    digest_data["insight_method"] = "gemini" if key else "heuristic"
    
    return digest_data
