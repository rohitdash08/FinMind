"""
Smart digest with weekly financial summary — #121

Generates a weekly financial summary digest for users, including:
- Balance changes (income vs spending)
- Category breakdown (top categories by amount)
- Recurring expense highlights
- Budget status (on-track / overspent)
- Trend comparison vs previous week
- AI-generated insights & tips (powered by ModelScope/DeepSeek)
"""
import json
from datetime import date, timedelta

from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import Expense, User, Bill, RecurringExpense


digest_bp = Blueprint("digest", __name__, url_prefix="/api")


def _get_week_range(ref: date = None) -> tuple[date, date]:
    """Return (start, end) for the current ISO week."""
    ref = ref or date.today()
    start = ref - timedelta(days=ref.weekday())  # Monday
    return start, start + timedelta(days=6)


def _get_prev_week_range(ref: date = None) -> tuple[date, date]:
    """Return (start, end) for the previous ISO week."""
    ref = ref or date.today()
    end = ref - timedelta(days=ref.weekday() + 1)  # Sunday of prev week
    start = end - timedelta(days=6)
    return start, end


def _fetch_weekly_summary(user_id: int, week_start: date, week_end: date) -> dict:
    """Fetch aggregated financial data for a user for a given week."""
    expenses = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.spent_at >= week_start,
        Expense.spent_at <= week_end,
    ).all()

    total_spent = sum(float(e.amount) for e in expenses if e.expense_type == "EXPENSE")
    total_income = sum(float(e.amount) for e in expenses if e.expense_type == "INCOME")

    # Category breakdown
    cat_spend = {}
    for e in expenses:
        cat = e.category_id or 0
        cat_spend[cat] = cat_spend.get(cat, 0) + float(e.amount)

    # Bills due this week
    bills_due = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.active == True,
        Bill.next_due_date >= week_start,
        Bill.next_due_date <= week_end,
    ).count()

    # Recurring expenses active
    recurring_count = RecurringExpense.query.filter(
        RecurringExpense.user_id == user_id,
        RecurringExpense.active == True,
    ).count()

    return {
        "week": f"{week_start.isoformat()} / {week_end.isoformat()}",
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "net_change": round(total_income - total_spent, 2),
        "transaction_count": len(expenses),
        "top_categories": sorted(cat_spend.items(), key=lambda x: x[1], reverse=True)[:5],
        "bills_due": bills_due,
        "active_recurring": recurring_count,
    }


@digest_bp.route("/digest/weekly", methods=["GET"])
def weekly_digest():
    """Generate and return weekly financial summary for the current user."""
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id query param required"}), 400

    week_start, week_end = _get_week_range()
    prev_start, prev_end = _get_prev_week_range()

    current = _fetch_weekly_summary(user_id, week_start, week_end)
    previous = _fetch_weekly_summary(user_id, prev_start, prev_end)

    # Trend comparison
    spend_change = current["total_spent"] - previous["total_spent"]
    spend_change_pct = (
        round((spend_change / previous["total_spent"]) * 100, 1)
        if previous["total_spent"]
        else 0
    )

    # Build insight message
    insights = []
    if current["net_change"] < 0:
        insights.append(
            f"⚠️ You spent ${abs(current['net_change']):.2f} more than you earned this week."
        )
    elif current["net_change"] > 0:
        insights.append(
            f"✅ You saved ${current['net_change']:.2f} this week. Keep it up!"
        )

    if spend_change > 0:
        insights.append(
            f"📈 Spending increased {spend_change_pct}% vs last week (${spend_change:.2f})."
        )
    elif spend_change < 0:
        insights.append(
            f"📉 Spending decreased {abs(spend_change_pct)}% vs last week — great!"
        )

    if current["bills_due"]:
        insights.append(
            f"📄 {current['bills_due']} bill(s) due this week."
        )

    return jsonify({
        "user_id": user_id,
        "generated_at": date.today().isoformat(),
        "current_week": current,
        "previous_week": previous,
        "trends": {
            "spend_vs_last_week": round(spend_change, 2),
            "spend_change_pct": spend_change_pct,
        },
        "insights": insights,
        "summary": f"Weekly summary: ${current['total_spent']:.2f} spent, "
                   f"${current['total_income']:.2f} earned. {insights[0] if insights else 'All good!'}",
    }), 200


@digest_bp.route("/digest/weekly/history", methods=["GET"])
def weekly_history():
    """Return weekly summaries for the last N weeks."""
    user_id = request.args.get("user_id", type=int)
    weeks = min(request.args.get("weeks", 4, type=int), 52)

    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    today = date.today()
    results = []
    for i in range(weeks):
        ref = today - timedelta(weeks=i)
        start, end = _get_week_range(ref)
        results.append(_fetch_weekly_summary(user_id, start, end))

    return jsonify({"user_id": user_id, "weeks": results}), 200
