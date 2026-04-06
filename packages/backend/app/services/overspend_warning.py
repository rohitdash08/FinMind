"""Category overspend early warning system (issue #117)."""
import logging
from datetime import date
from sqlalchemy import extract, func
from dateutil.relativedelta import relativedelta
from ..extensions import db
from ..models import Expense, Category, Budget

logger = logging.getLogger("finmind.overspend")


def check_overspend_warnings(user_id: int) -> dict:
    today = date.today()
    year, month = today.year, today.month
    days_in_month = (date(year, month % 12 + 1, 1) - relativedelta(days=1)).day if month < 12 else 31
    day_of_month = today.day
    month_progress = day_of_month / days_in_month

    # Actual spend per category this month
    rows = (db.session.query(
                func.coalesce(Category.name, "Uncategorized").label("name"),
                Category.id.label("cat_id"),
                func.sum(Expense.amount).label("spent"))
            .outerjoin(Category, (Category.id == Expense.category_id) & (Category.user_id == user_id))
            .filter(Expense.user_id == user_id,
                    extract("year", Expense.spent_at) == year,
                    extract("month", Expense.spent_at) == month,
                    Expense.expense_type != "INCOME")
            .group_by(Expense.category_id, Category.id, Category.name).all())

    warnings = []
    for r in rows:
        spent = float(r.spent or 0)
        # Try to find a budget limit for this category
        budget = None
        if r.cat_id:
            budget = db.session.query(Budget).filter_by(
                user_id=user_id, category_id=r.cat_id).first()

        if budget and float(budget.limit_amount) > 0:
            limit = float(budget.limit_amount)
            pct_used = spent / limit
            projected = spent / month_progress if month_progress > 0 else spent

            if pct_used >= 1.0:
                level = "exceeded"
            elif pct_used >= 0.85:
                level = "critical"
            elif projected > limit:
                level = "on_track_to_exceed"
            elif pct_used >= 0.65:
                level = "warning"
            else:
                continue

            warnings.append({
                "category": r.name, "spent": round(spent, 2),
                "budget": round(limit, 2), "pct_used": round(pct_used * 100, 1),
                "projected_eom": round(projected, 2),
                "level": level,
                "message": _msg(r.name, level, spent, limit, projected),
            })
        else:
            # No budget set — flag if pace is unusually high vs prior months
            prev = float(db.session.query(func.coalesce(func.sum(Expense.amount), 0))
                         .join(Category, Expense.category_id == Category.id)
                         .filter(Expense.user_id == user_id,
                                 Category.name == r.name,
                                 extract("year", Expense.spent_at) == (today - relativedelta(months=1)).year,
                                 extract("month", Expense.spent_at) == (today - relativedelta(months=1)).month,
                                 Expense.expense_type != "INCOME").scalar() or 0)
            if prev > 0:
                projected = spent / month_progress if month_progress > 0 else spent
                if projected > prev * 1.5:
                    warnings.append({
                        "category": r.name, "spent": round(spent, 2),
                        "budget": None, "pct_used": None,
                        "projected_eom": round(projected, 2),
                        "level": "pace_alert",
                        "message": f"{r.name}: on pace for ${projected:.0f} vs ${prev:.0f} last month (+{((projected/prev)-1)*100:.0f}%)",
                    })

    warnings.sort(key=lambda x: {"exceeded":0,"critical":1,"on_track_to_exceed":2,"warning":3,"pace_alert":4}.get(x["level"],5))
    return {"period": f"{year}-{month:02d}", "warnings": warnings, "warning_count": len(warnings),
            "month_progress_pct": round(month_progress * 100, 1)}


def _msg(cat, level, spent, limit, projected):
    if level == "exceeded": return f"{cat}: EXCEEDED budget (${spent:.0f} of ${limit:.0f})"
    if level == "critical": return f"{cat}: {spent/limit*100:.0f}% of budget used with {100-round(spent/limit*100)}% of month left"
    if level == "on_track_to_exceed": return f"{cat}: on pace to reach ${projected:.0f} vs ${limit:.0f} budget"
    return f"{cat}: {spent/limit*100:.0f}% of budget used"
