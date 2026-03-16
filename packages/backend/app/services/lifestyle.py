"""
Lifestyle inflation detection service.

Compares spending per category between two equal time windows (recent vs
previous) and surfaces categories where spending has grown materially,
indicating lifestyle inflation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Expense, Category


def _monthly_totals(user_id: int, months: int) -> dict[int, dict[str, Decimal]]:
    """
    Return {category_id: {YYYY-MM: total_spent}} for EXPENSE rows only,
    covering the last `months` calendar months up to today.
    """
    today = date.today()
    # Build a simple list of (year, month) for the last `months` months
    periods: list[tuple[int, int]] = []
    y, m = today.year, today.month
    for _ in range(months):
        periods.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    if not periods:
        return {}

    oldest_year, oldest_month = periods[-1]
    newest_year, newest_month = periods[0]

    rows = (
        db.session.query(
            Expense.category_id,
            extract("year", Expense.spent_at).label("yr"),
            extract("month", Expense.spent_at).label("mo"),
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.expense_type == "EXPENSE",
            Expense.category_id.isnot(None),
        )
        .filter(
            # Keep rows within the rolling window
            db.or_(
                extract("year", Expense.spent_at) > oldest_year,
                db.and_(
                    extract("year", Expense.spent_at) == oldest_year,
                    extract("month", Expense.spent_at) >= oldest_month,
                ),
            ),
            db.or_(
                extract("year", Expense.spent_at) < newest_year,
                db.and_(
                    extract("year", Expense.spent_at) == newest_year,
                    extract("month", Expense.spent_at) <= newest_month,
                ),
            ),
        )
        .group_by(
            Expense.category_id,
            extract("year", Expense.spent_at),
            extract("month", Expense.spent_at),
        )
        .all()
    )

    result: dict[int, dict[str, Decimal]] = defaultdict(dict)
    for row in rows:
        ym = f"{int(row.yr):04d}-{int(row.mo):02d}"
        result[int(row.category_id)][ym] = Decimal(str(row.total))
    return result


def _category_names(user_id: int) -> dict[int, str]:
    rows = db.session.query(Category.id, Category.name).filter_by(user_id=user_id).all()
    return {r.id: r.name for r in rows}


def detect_lifestyle_inflation(
    user_id: int,
    window_months: int = 3,
    inflation_threshold_pct: float = 10.0,
) -> dict:
    """
    Detect lifestyle inflation for a user.

    Compares average monthly spend in the most recent `window_months` months
    against the previous `window_months` months.  Categories where spending
    grew by more than `inflation_threshold_pct` percent are returned as
    inflation signals.

    Returns a dict with:
      - inflated_categories: list of category signals (sorted by pct_change desc)
      - stable_categories: categories with no significant growth
      - summary: counts and total_extra_monthly_spend
      - window_months: echo input param
    """
    total_window = window_months * 2
    monthly = _monthly_totals(user_id, total_window)
    names = _category_names(user_id)

    today = date.today()

    # Build ordered list of YYYY-MM for recent and previous windows
    recent_months: list[str] = []
    previous_months: list[str] = []
    y, m = today.year, today.month
    for i in range(total_window):
        ym = f"{y:04d}-{m:02d}"
        if i < window_months:
            recent_months.append(ym)
        else:
            previous_months.append(ym)
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    inflated: list[dict] = []
    stable: list[dict] = []

    all_cat_ids = set(monthly.keys())
    for cat_id in all_cat_ids:
        totals = monthly[cat_id]
        recent_values = [float(totals.get(mo, Decimal("0"))) for mo in recent_months]
        prev_values = [float(totals.get(mo, Decimal("0"))) for mo in previous_months]

        recent_avg = sum(recent_values) / len(recent_months)
        prev_avg = sum(prev_values) / len(previous_months)

        # Need at least some spending in the previous window to compare
        if prev_avg < 0.01:
            continue

        pct_change = ((recent_avg - prev_avg) / prev_avg) * 100.0
        abs_change = recent_avg - prev_avg

        # Build monthly trend (all periods, ordered oldest→newest)
        trend = []
        for mo in reversed(previous_months):
            trend.append({"month": mo, "amount": float(totals.get(mo, Decimal("0")))})
        for mo in reversed(recent_months):
            trend.append({"month": mo, "amount": float(totals.get(mo, Decimal("0")))})

        entry = {
            "category_id": cat_id,
            "category_name": names.get(cat_id, "Unknown"),
            "recent_avg_monthly": round(recent_avg, 2),
            "previous_avg_monthly": round(prev_avg, 2),
            "pct_change": round(pct_change, 1),
            "abs_change_monthly": round(abs_change, 2),
            "annualised_extra": round(abs_change * 12, 2),
            "trend": trend,
        }

        if pct_change >= inflation_threshold_pct:
            inflated.append(entry)
        else:
            stable.append(entry)

    inflated.sort(key=lambda x: x["pct_change"], reverse=True)
    stable.sort(key=lambda x: x["pct_change"], reverse=True)

    total_extra = sum(e["abs_change_monthly"] for e in inflated)

    return {
        "inflated_categories": inflated,
        "stable_categories": stable,
        "summary": {
            "inflated_count": len(inflated),
            "stable_count": len(stable),
            "total_extra_monthly_spend": round(total_extra, 2),
            "total_extra_annual_spend": round(total_extra * 12, 2),
        },
        "window_months": window_months,
        "inflation_threshold_pct": inflation_threshold_pct,
    }
