"""
savings.py — Savings opportunity detection engine.

Identifies categories where the user is currently spending above their own
historical average, and surfaces actionable cut recommendations.

Public API:
    detect_savings_opportunities(uid, session, months, reference_date) -> dict
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models import Category, Expense

logger = logging.getLogger("finmind.savings")

_OVERSPEND_RATIO = 1.20   # 20% above historical average = opportunity
_HIGH_SHARE_PCT  = 0.25   # >25% of total spend = high-share category


def _category_spend_for_month(uid: int, session: Session, year: int, month: int) -> dict[int | None, float]:
    rows = (
        session.query(Expense.category_id, func.sum(Expense.amount).label("total"))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {r.category_id: float(r.total) for r in rows}


def _prior_months(reference: date, months: int) -> list[tuple[int, int]]:
    """Return list of (year, month) tuples for the N months before reference month."""
    result = []
    y, m = reference.year, reference.month
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    for _ in range(months):
        result.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(result))


def detect_savings_opportunities(
    uid: int,
    session: Session,
    months: int = 3,
    reference_date: date | None = None,
) -> dict:
    """
    Detect categories where the user can realistically save money.

    Returns:
    {
      "reference_month": "YYYY-MM",
      "comparison_months": ["YYYY-MM", ...],
      "total_current_spend": <float>,
      "total_potential_savings": <float>,
      "opportunities": [
        {
          "category_id": <int|null>,
          "category_name": <str>,
          "current_spend": <float>,
          "historical_avg": <float>,
          "overage": <float>,
          "overage_pct": <float>,
          "share_of_total": <float>,
          "flags": ["HIGH_SPEND", "HIGH_SHARE"],  # one or both
          "recommendation": "<str>",
        }, ...
      ],
      "insights": ["<str>", ...]
    }
    """
    ref = reference_date or date.today()
    months = max(1, min(months, 12))

    # Current month spend
    cur_spend = _category_spend_for_month(uid, session, ref.year, ref.month)
    total_current = sum(cur_spend.values())

    # Prior months
    prior = _prior_months(ref, months)
    comparison_months = [f"{y}-{m:02d}" for y, m in prior]

    # Build historical average per category
    hist: dict[int | None, list[float]] = {}
    for y, m in prior:
        month_data = _category_spend_for_month(uid, session, y, m)
        all_cats = set(list(month_data.keys()) + list(cur_spend.keys()))
        for cat_id in all_cats:
            hist.setdefault(cat_id, []).append(month_data.get(cat_id, 0.0))

    hist_avg: dict[int | None, float] = {
        cat_id: sum(vals) / len(vals) for cat_id, vals in hist.items()
    }

    # Category names
    cat_rows = session.query(Category.id, Category.name).filter_by(user_id=uid).all()
    cat_names: dict[int | None, str] = {r.id: r.name for r in cat_rows}
    cat_names[None] = "Uncategorised"

    opportunities = []
    total_potential_savings = 0.0

    for cat_id, current in cur_spend.items():
        avg = hist_avg.get(cat_id, 0.0)
        share = current / total_current if total_current > 0 else 0.0

        flags = []
        if avg > 0 and current > avg * _OVERSPEND_RATIO:
            flags.append("HIGH_SPEND")
        if share >= _HIGH_SHARE_PCT:
            flags.append("HIGH_SHARE")

        if not flags:
            continue

        overage = max(0.0, current - avg) if avg > 0 else 0.0
        overage_pct = round((current / avg - 1) * 100, 1) if avg > 0 else None
        total_potential_savings += overage

        cat_name = cat_names.get(cat_id, f"Category {cat_id}")

        # Build recommendation
        if "HIGH_SPEND" in flags and avg > 0:
            rec = (
                f"You're spending {overage_pct:.1f}% above your usual on {cat_name}. "
                f"Cutting back to your {months}-month average would save "
                f"{overage:,.2f} this month."
            )
        elif "HIGH_SHARE" in flags:
            rec = (
                f"{cat_name} accounts for {share * 100:.1f}% of your spending. "
                f"Reducing it by 10–15% could free up meaningful budget."
            )
        else:
            rec = f"Review {cat_name} spending for potential savings."

        opportunities.append({
            "category_id": cat_id,
            "category_name": cat_name,
            "current_spend": round(current, 2),
            "historical_avg": round(avg, 2),
            "overage": round(overage, 2),
            "overage_pct": overage_pct,
            "share_of_total": round(share, 4),
            "flags": flags,
            "recommendation": rec,
        })

    # Sort: HIGH_SPEND+HIGH_SHARE first, then by overage desc
    opportunities.sort(key=lambda o: (
        -len(o["flags"]),
        -o["overage"],
    ))

    # Insights
    insights = []
    if opportunities:
        top = opportunities[0]
        insights.append(
            f"Biggest savings opportunity: {top['category_name']} "
            f"({top['overage_pct']:+.1f}% vs average)."
            if top["overage_pct"] is not None
            else f"Biggest opportunity: {top['category_name']}."
        )
        if total_potential_savings > 0:
            insights.append(
                f"Total potential monthly savings: {total_potential_savings:,.2f} "
                f"(based on your {months}-month average)."
            )
    else:
        insights.append("Spending is in line with your recent history — no major savings opportunities detected.")

    logger.info(
        "Savings opportunities user=%s month=%s-%02d opportunities=%d potential_savings=%.2f",
        uid, ref.year, ref.month, len(opportunities), total_potential_savings,
    )

    return {
        "reference_month": f"{ref.year}-{ref.month:02d}",
        "comparison_months": comparison_months,
        "total_current_spend": round(total_current, 2),
        "total_potential_savings": round(total_potential_savings, 2),
        "opportunities": opportunities,
        "insights": insights,
    }
