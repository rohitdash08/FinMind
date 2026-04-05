"""
Savings opportunity detection engine (issue #119).
Analyzes spending patterns to find potential savings.
"""
import logging
from datetime import date
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.savings_opp")

SUBSCRIPTION_KEYWORDS = {"netflix","spotify","hulu","disney","prime","apple","youtube premium",
                          "gym","membership","subscription","saas","monthly"}
DINING_KEYWORDS = {"restaurant","dining","food delivery","doordash","uber eats","grubhub","zomato"}


def detect_opportunities(user_id: int, year: int, month: int) -> dict:
    rows = (
        db.session.query(
            func.coalesce(Category.name, "Uncategorized").label("cat"),
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("txn_count"),
        )
        .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
        .filter(
            Expense.user_id == user_id,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id, Category.name).all()
    )

    total_spend = sum(float(r.total or 0) for r in rows)
    opportunities = []

    for r in rows:
        amt = float(r.total or 0)
        cat = (r.cat or "").lower()
        pct = round(amt / total_spend * 100, 1) if total_spend else 0

        # High-frequency small transactions (likely subscriptions)
        if r.txn_count >= 3 and amt < 100:
            opportunities.append({
                "type": "subscription_audit",
                "category": r.cat,
                "amount": round(amt, 2),
                "message": f"'{r.cat}' has {r.txn_count} small charges (${amt:.0f}/mo). Review for unused subscriptions.",
                "potential_saving": round(amt * 0.5, 2),
            })
        # High dining spend
        if any(k in cat for k in DINING_KEYWORDS) and pct > 15:
            opportunities.append({
                "type": "dining_reduction",
                "category": r.cat,
                "amount": round(amt, 2),
                "message": f"Dining at {pct}% of budget. Cooking at home could save ~${amt*0.4:.0f}/mo.",
                "potential_saving": round(amt * 0.4, 2),
            })
        # Single category > 30% of budget (non-essential)
        if pct > 30 and cat not in {"rent","mortgage","housing"}:
            opportunities.append({
                "type": "category_dominance",
                "category": r.cat,
                "amount": round(amt, 2),
                "message": f"'{r.cat}' is {pct}% of monthly spend. Consider a budget cap.",
                "potential_saving": round(amt * 0.2, 2),
            })

    total_potential = round(sum(o["potential_saving"] for o in opportunities), 2)
    return {
        "period": f"{year}-{month:02d}",
        "opportunities": sorted(opportunities, key=lambda x: -x["potential_saving"]),
        "total_potential_saving": total_potential,
        "summary": f"Found {len(opportunities)} saving opportunity{'s' if len(opportunities)!=1 else ''}. Potential: ${total_potential}/mo.",
    }
