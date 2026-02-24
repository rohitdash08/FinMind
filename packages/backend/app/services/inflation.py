"""
inflation.py — Lifestyle inflation detection service.

Analyses month-over-month spending trends to detect lifestyle inflation:
consistent spending growth across categories, often without a matching
income increase.

Public API:
    detect_lifestyle_inflation(uid, session, months, reference_date) -> dict
"""
from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from ..models import Category, Expense

logger = logging.getLogger("finmind.inflation")

_INFLATION_WARNING_THRESHOLD = 0.05   # 5%+ MoM growth = trending up
_CONSISTENT_MONTHS = 2                # >= N consecutive up months = "inflating"


def _ym_range(reference: date, months: int) -> list[str]:
    """Return list of YYYY-MM strings for the `months` months ending before reference month."""
    result = []
    y, m = reference.year, reference.month
    # Step back one month to exclude the current (partial) month
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    for _ in range(months):
        result.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(result))   # oldest first


def _monthly_category_spend(uid: int, session: Session, ym: str) -> dict[int | None, float]:
    """Return {category_id: total_spend} for a given month (INCOME excluded)."""
    year, month = map(int, ym.split("-"))
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


def _monthly_totals(uid: int, session: Session, ym: str) -> tuple[float, float]:
    """Return (total_income, total_spend) for a given month."""
    year, month = map(int, ym.split("-"))
    income = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type == "INCOME",
    ).scalar()
    expenses = session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
        Expense.user_id == uid,
        extract("year", Expense.spent_at) == year,
        extract("month", Expense.spent_at) == month,
        Expense.expense_type != "INCOME",
    ).scalar()
    return float(income or 0), float(expenses or 0)


def _pct_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return round((new - old) / old * 100, 1)


def _consecutive_increases(values: list[float]) -> int:
    """Count trailing consecutive month-over-month increases."""
    count = 0
    for i in range(len(values) - 1, 0, -1):
        if values[i] > values[i - 1]:
            count += 1
        else:
            break
    return count


def detect_lifestyle_inflation(
    uid: int,
    session: Session,
    months: int = 6,
    reference_date: date | None = None,
) -> dict:
    """
    Detect lifestyle inflation by analysing spending trends over the past N months.

    Returns:
    {
      "period_months": <int>,
      "months_analysed": ["YYYY-MM", ...],
      "inflation_score": <0-100>,        # 0=no inflation, 100=severe
      "overall_trend": "UP"|"DOWN"|"FLAT"|"INSUFFICIENT_DATA",
      "monthly_totals": [
        {"month": "YYYY-MM", "income": <float>, "spend": <float>, "net": <float>}, ...
      ],
      "inflating_categories": [
        {
          "category_id": <int|null>,
          "category_name": <str>,
          "monthly_spend": [<float>, ...],
          "consecutive_increases": <int>,
          "total_growth_pct": <float|null>,
          "status": "INFLATING"|"VOLATILE"|"STABLE"
        }, ...
      ],
      "insights": ["<str>", ...]
    }
    """
    ref = reference_date or date.today()
    months = max(2, min(months, 12))  # clamp 2-12
    period = _ym_range(ref, months)

    if not period:
        return {"error": "insufficient data period"}

    # Gather category name map
    cat_rows = session.query(Category.id, Category.name).filter_by(user_id=uid).all()
    cat_names: dict[int | None, str] = {r.id: r.name for r in cat_rows}
    cat_names[None] = "Uncategorised"

    # Collect monthly totals and per-category spend
    monthly_totals = []
    all_category_spend: dict[int | None, list[float]] = {}

    for ym in period:
        income, spend = _monthly_totals(uid, session, ym)
        monthly_totals.append({
            "month": ym,
            "income": round(income, 2),
            "spend": round(spend, 2),
            "net": round(income - spend, 2),
        })
        cat_spend = _monthly_category_spend(uid, session, ym)
        # Ensure all known categories are represented (0 if no spend)
        for cat_id in set(list(cat_spend.keys()) + list(all_category_spend.keys())):
            if cat_id not in all_category_spend:
                all_category_spend[cat_id] = [0.0] * len(period)
            idx = period.index(ym)
            all_category_spend[cat_id][idx] = cat_spend.get(cat_id, 0.0)

    # Overall trend
    spend_values = [m["spend"] for m in monthly_totals]
    if len(spend_values) < 2 or all(v == 0 for v in spend_values):
        overall_trend = "INSUFFICIENT_DATA"
    else:
        first_half = sum(spend_values[:len(spend_values)//2]) / (len(spend_values)//2)
        second_half = sum(spend_values[len(spend_values)//2:]) / (len(spend_values) - len(spend_values)//2)
        if second_half > first_half * 1.03:
            overall_trend = "UP"
        elif second_half < first_half * 0.97:
            overall_trend = "DOWN"
        else:
            overall_trend = "FLAT"

    # Analyse per-category inflation
    inflating_categories = []
    for cat_id, values in all_category_spend.items():
        if all(v == 0 for v in values):
            continue  # skip completely inactive categories
        consec = _consecutive_increases(values)
        first_nonzero = next((v for v in values if v > 0), 0)
        last_val = values[-1]
        total_growth = _pct_change(first_nonzero, last_val)

        if consec >= _CONSISTENT_MONTHS:
            status = "INFLATING"
        elif total_growth is not None and total_growth > 20:
            status = "VOLATILE"
        else:
            status = "STABLE"

        inflating_categories.append({
            "category_id": cat_id,
            "category_name": cat_names.get(cat_id, f"Category {cat_id}"),
            "monthly_spend": [round(v, 2) for v in values],
            "consecutive_increases": consec,
            "total_growth_pct": total_growth,
            "status": status,
        })

    # Sort: INFLATING first, then by consecutive_increases desc
    inflating_categories.sort(key=lambda c: (
        -int(c["status"] == "INFLATING"),
        -c["consecutive_increases"],
    ))

    # Inflation score (0-100)
    n_inflating = sum(1 for c in inflating_categories if c["status"] == "INFLATING")
    n_total = len(inflating_categories) or 1
    base_score = min(100, int((n_inflating / n_total) * 60))
    if overall_trend == "UP":
        base_score = min(100, base_score + 25)
    avg_growth = 0.0
    growth_values = [
        c["total_growth_pct"] for c in inflating_categories
        if c["total_growth_pct"] is not None
    ]
    if growth_values:
        avg_growth = sum(growth_values) / len(growth_values)
        base_score = min(100, base_score + int(min(15, max(0, avg_growth / 10))))
    inflation_score = base_score

    # Plain-English insights
    insights = []
    if overall_trend == "UP":
        first_spend = spend_values[0]
        last_spend = spend_values[-1]
        pct = _pct_change(first_spend, last_spend)
        if pct is not None:
            insights.append(
                f"Total spending has increased {pct:+.1f}% over the past {months} months "
                f"({monthly_totals[0]['month']} → {monthly_totals[-1]['month']})."
            )
    elif overall_trend == "DOWN":
        insights.append(f"Overall spending is trending down — good discipline over {months} months.")
    elif overall_trend == "FLAT":
        insights.append(f"Spending is broadly stable over the past {months} months.")

    inflating_names = [c["category_name"] for c in inflating_categories if c["status"] == "INFLATING"]
    if inflating_names:
        insights.append(
            f"Lifestyle inflation detected in: {', '.join(inflating_names[:3])}."
            + (" And more." if len(inflating_names) > 3 else "")
        )

    # Income vs spend divergence
    income_values = [m["income"] for m in monthly_totals if m["income"] > 0]
    if income_values and overall_trend == "UP":
        avg_income = sum(income_values) / len(income_values)
        avg_spend = sum(spend_values) / len(spend_values)
        if avg_spend > avg_income * 0.9:
            insights.append(
                "Spending is close to or exceeding income on average — consider reviewing discretionary categories."
            )

    if not insights:
        insights.append("No significant lifestyle inflation detected in this period.")

    logger.info(
        "Inflation analysis user=%s months=%s score=%d trend=%s inflating=%d",
        uid, months, inflation_score, overall_trend, n_inflating,
    )

    return {
        "period_months": months,
        "months_analysed": period,
        "inflation_score": inflation_score,
        "overall_trend": overall_trend,
        "monthly_totals": monthly_totals,
        "inflating_categories": inflating_categories,
        "insights": insights,
    }
