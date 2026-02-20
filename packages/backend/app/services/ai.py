from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense
from ..config import Settings

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None


_settings = Settings()


def _heuristic_budget(uid: int, ym: str):
    year, month = map(int, ym.split("-"))
    total = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .scalar()
    )
    # Suggest 90% of last spend with 50/30/20 breakdown
    target = float(total) * 0.9 if total else 500.0
    return {
        "month": ym,
        "suggested_total": round(target, 2),
        "breakdown": {
            "needs": round(target * 0.5, 2),
            "wants": round(target * 0.3, 2),
            "savings": round(target * 0.2, 2),
        },
        "method": "heuristic",
    }


def monthly_budget_suggestion(uid: int, ym: str):
    if _settings.openai_api_key and OpenAI:
        try:
            client = OpenAI(api_key=_settings.openai_api_key)
            year, month = map(int, ym.split("-"))
            rows = (
                db.session.query(Expense.category_id, func.sum(Expense.amount))
                .filter(
                    Expense.user_id == uid,
                    extract("year", Expense.spent_at) == year,
                    extract("month", Expense.spent_at) == month,
                )
                .group_by(Expense.category_id)
                .all()
            )
            categories = {str(k or "uncat"): float(v) for k, v in rows}
            prompt = (
                "Given the following monthly spend by category, suggest a "
                "reasonable budget for next month using the 50/30/20 rule as a "
                "baseline and add 2 actionable tips.\n"
                f"Data: {categories}\nReturn JSON with fields: suggested_total, "
                "breakdown(needs,wants,savings), tips(list)."
            )
            # Use Responses API for determinism
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content
            import json

            obj = json.loads(content)
            obj["month"] = ym
            obj["method"] = "openai"
            return obj
        except Exception:
            pass
    return _heuristic_budget(uid, ym)

def weekly_digest(uid: int):
    """
    Generate a smart weekly digest with spending trends and insights.
    """
    from datetime import datetime, timedelta
    today = date.today()
    start_of_week = today - timedelta(days=7)
    
    # Fetch expenses from the last 7 days
    rows = (
        db.session.query(Expense.category_id, func.sum(Expense.amount))
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= start_of_week,
            Expense.spent_at <= today,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    
    total_spend = sum(float(v) for _, v in rows)
    categories = {str(k or "uncat"): float(v) for k, v in rows}
    
    if _settings.openai_api_key and OpenAI:
        try:
            client = OpenAI(api_key=_settings.openai_api_key)
            prompt = (
                "Analyze the following weekly spending data and provide 3 concise "
                "insights/trends and 1 priority recommendation for the user.\n"
                f"Total Spend: {total_spend}\nBreakdown: {categories}\n"
                "Return JSON with fields: total_spend, insights(list), recommendation(str)."
            )
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                temperature=0.3,
                messages=[{"role": "user", "content": prompt}],
            )
            import json
            obj = json.loads(resp.choices[0].message.content)
            obj["period"] = f"{start_of_week.isoformat()} to {today.isoformat()}"
            obj["method"] = "openai"
            return obj
        except Exception:
            pass
            
    # Fallback heuristic digest
    return {
        "total_spend": round(total_spend, 2),
        "period": f"{start_of_week.isoformat()} to {today.isoformat()}",
        "insights": [
            f"You spent a total of {total_spend:.2f} this week.",
            "Top category: " + (max(categories, key=categories.get) if categories else "None"),
        ],
        "recommendation": "Track your daily expenses to get more precise AI insights." if total_spend > 0 else "Great job keeping your spending at zero this week!",
        "method": "heuristic"
    }
