"""Autonomous Budget Optimization service for FinMind (#92)."""
import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.budget")


def _get_category_spending(uid: int, months: int = 3) -> list[dict]:
    """Get average monthly spending per category over the past N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    rows = (
        db.session.query(
            Expense.category_id,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("count"),
        )
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= cutoff,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )

    result = []
    for row in rows:
        cat = db.session.get(Category, row.category_id) if row.category_id else None
        result.append({
            "category_id": row.category_id,
            "category_name": cat.name if cat else "Uncategorized",
            "total_spent": float(row.total),
            "monthly_avg": round(float(row.total) / months, 2),
            "transaction_count": row.count,
        })

    return sorted(result, key=lambda x: x["monthly_avg"], reverse=True)


def _get_income_average(uid: int, months: int = 3) -> float:
    """Get average monthly income over the past N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    total = db.session.query(
        func.coalesce(func.sum(Expense.amount), 0)
    ).filter(
        Expense.user_id == uid,
        Expense.spent_at >= cutoff,
        Expense.expense_type == "INCOME",
    ).scalar()
    return float(total or 0) / months


def _get_month_over_month_change(uid: int, category_id: Optional[int]) -> float:
    """Calculate MoM spending change percentage for a category."""
    today = date.today()
    cur_year, cur_month = today.year, today.month
    prev_month = 12 if cur_month == 1 else cur_month - 1
    prev_year = today.year - 1 if cur_month == 1 else today.year

    def month_spend(year, month):
        q = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        if category_id is not None:
            q = q.filter(Expense.category_id == category_id)
        else:
            q = q.filter(Expense.category_id.is_(None))
        return float(q.scalar() or 0)

    cur = month_spend(cur_year, cur_month)
    prev = month_spend(prev_year, prev_month)

    if prev == 0:
        return 0.0
    return round(((cur - prev) / prev) * 100, 1)


def optimize_budget(uid: int, target_savings_pct: float = 20.0, months: int = 3) -> dict:
    """
    Suggest autonomous budget optimizations based on spending patterns.

    Strategy:
    1. Calculate current avg monthly income and expenses per category
    2. Apply the 50/30/20 rule (needs/wants/savings) as target
    3. Detect overspending categories and suggest reductions
    4. Detect stable/underspent categories (safe to reallocate)
    5. Generate actionable recommendations

    Args:
        uid: User ID
        target_savings_pct: Target savings % of income (default 20%)
        months: Historical months to analyze (default 3)

    Returns:
        {
            "current_state": {...},
            "target_state": {...},
            "recommendations": [...],
            "estimated_monthly_savings": float
        }
    """
    target_savings_pct = max(5.0, min(50.0, target_savings_pct))

    avg_income = _get_income_average(uid, months)
    category_spending = _get_category_spending(uid, months)

    total_monthly_expenses = sum(c["monthly_avg"] for c in category_spending)
    current_savings = avg_income - total_monthly_expenses
    current_savings_pct = (current_savings / avg_income * 100) if avg_income > 0 else 0

    # Target budget allocation
    target_savings = avg_income * (target_savings_pct / 100)
    target_expenses = avg_income - target_savings
    savings_gap = target_savings - current_savings

    # Generate recommendations
    recommendations = []

    if savings_gap <= 0:
        recommendations.append({
            "type": "achievement",
            "priority": "info",
            "message": f"You are already saving {round(current_savings_pct, 1)}% of income, exceeding your {target_savings_pct}% target.",
            "category_id": None,
            "category_name": None,
            "current_amount": round(current_savings, 2),
            "suggested_amount": round(target_savings, 2),
            "potential_monthly_saving": 0,
        })
    else:
        # Find categories with month-over-month increase (overspending trend)
        overspending = []
        for cat in category_spending:
            mom = _get_month_over_month_change(uid, cat["category_id"])
            if mom > 10:  # More than 10% MoM increase
                overspending.append({**cat, "mom_change_pct": mom})

        # Sort by MoM change, worst first
        overspending.sort(key=lambda x: x["mom_change_pct"], reverse=True)

        remaining_gap = savings_gap
        for cat in overspending:
            if remaining_gap <= 0:
                break
            # Suggest reducing to last month's level
            reduction = min(
                cat["monthly_avg"] * (cat["mom_change_pct"] / 100 * 0.7),
                remaining_gap
            )
            if reduction > 50:  # Only suggest meaningful reductions
                suggested = cat["monthly_avg"] - reduction
                recommendations.append({
                    "type": "reduce",
                    "priority": "high" if cat["mom_change_pct"] > 25 else "medium",
                    "message": f"{cat['category_name']} spending increased {cat['mom_change_pct']}% last month. Reducing to previous levels could save {round(reduction, 2)}/month.",
                    "category_id": cat["category_id"],
                    "category_name": cat["category_name"],
                    "current_amount": round(cat["monthly_avg"], 2),
                    "suggested_amount": round(suggested, 2),
                    "potential_monthly_saving": round(reduction, 2),
                })
                remaining_gap -= reduction

        # If still a gap, suggest top spending categories
        if remaining_gap > 0 and category_spending:
            for cat in category_spending[:3]:
                if remaining_gap <= 0:
                    break
                # Suggest 10% reduction
                reduction = cat["monthly_avg"] * 0.10
                if reduction > 20:
                    recommendations.append({
                        "type": "reduce",
                        "priority": "low",
                        "message": f"A 10% reduction in {cat['category_name']} spending could save {round(reduction, 2)}/month.",
                        "category_id": cat["category_id"],
                        "category_name": cat["category_name"],
                        "current_amount": round(cat["monthly_avg"], 2),
                        "suggested_amount": round(cat["monthly_avg"] * 0.90, 2),
                        "potential_monthly_saving": round(reduction, 2),
                    })
                    remaining_gap -= reduction

    total_potential_saving = sum(r.get("potential_monthly_saving", 0) for r in recommendations)
    projected_savings_pct = ((current_savings + total_potential_saving) / avg_income * 100) if avg_income > 0 else 0

    return {
        "current_state": {
            "avg_monthly_income": round(avg_income, 2),
            "avg_monthly_expenses": round(total_monthly_expenses, 2),
            "avg_monthly_savings": round(current_savings, 2),
            "savings_percentage": round(current_savings_pct, 1),
            "analysis_months": months,
        },
        "target_state": {
            "target_savings_pct": target_savings_pct,
            "target_monthly_savings": round(target_savings, 2),
            "savings_gap": round(savings_gap, 2),
        },
        "recommendations": recommendations,
        "estimated_monthly_savings": round(total_potential_saving, 2),
        "projected_savings_pct": round(projected_savings_pct, 1),
        "category_breakdown": [
            {
                "category_id": c["category_id"],
                "category_name": c["category_name"],
                "monthly_avg": c["monthly_avg"],
                "pct_of_expenses": round(c["monthly_avg"] / total_monthly_expenses * 100, 1) if total_monthly_expenses > 0 else 0,
            }
            for c in category_spending[:10]
        ],
    }

