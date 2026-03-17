"""
Advanced Cash Flow Forecasting (Issue #93).

Predicts future cash flow trends using:
- Historical monthly income/expense averages (baseline)
- Seasonal pattern detection (month-of-year variance)
- Irregular expense detection (one-off large outliers excluded from baseline)
- Upcoming bill obligations pulled from the bills table
- Confidence indicators (high / medium / low based on data richness)

No ML — deterministic statistical model (mean ± std deviation).
Pure Python + SQLAlchemy.

Public API
----------
forecast_cashflow(uid, horizon_months, anchor) → ForecastResult dict
"""

from __future__ import annotations

import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Bill, Expense

logger = logging.getLogger("finmind.cashflow")

# ── Constants ─────────────────────────────────────────────────────────────────

_HISTORY_MONTHS      = 12   # months of history used to build the model
_OUTLIER_STDDEV      = 2.0  # expense is "irregular" if > mean + N*std
_MIN_MONTHS_HIGH_CONF = 6   # need at least 6 months of data for high confidence
_MIN_MONTHS_MED_CONF  = 3   # need at least 3 months for medium confidence

# ── Data gathering ────────────────────────────────────────────────────────────

def _monthly_totals(uid: int, months: int, anchor: date) -> list[dict]:
    """Return list of {year, month, income, expenses} for the last *months* months."""
    results = []
    y, m = anchor.year, anchor.month
    for _ in range(months):
        inc = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "INCOME",
            )
            .scalar() or 0
        )
        exp = float(
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "EXPENSE",
            )
            .scalar() or 0
        )
        results.append({"year": y, "month": m, "income": inc, "expenses": exp})
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(results))


def _upcoming_bills(uid: int, anchor: date, horizon_months: int) -> dict[str, float]:
    """Return {YYYY-MM: total_bill_amount} for upcoming active bills."""
    horizon_end = date(
        anchor.year + (anchor.month + horizon_months - 1) // 12,
        (anchor.month + horizon_months - 1) % 12 + 1,
        1,
    )
    bills = (
        db.session.query(Bill)
        .filter(
            Bill.user_id == uid,
            Bill.active == True,
            Bill.next_due_date >= anchor,
            Bill.next_due_date <= horizon_end,
        )
        .all()
    )
    totals: dict[str, float] = defaultdict(float)
    for b in bills:
        key = f"{b.next_due_date.year:04d}-{b.next_due_date.month:02d}"
        totals[key] += float(b.amount)
    return dict(totals)


# ── Statistical model ─────────────────────────────────────────────────────────

def _remove_outliers(values: list[float]) -> list[float]:
    """Remove values that are extreme outliers (> mean + N*std)."""
    if len(values) < 3:
        return values
    mu  = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0
    if std == 0:
        return values
    return [v for v in values if v <= mu + _OUTLIER_STDDEV * std]


def _seasonal_index(month_data: list[dict], month_of_year: int) -> float:
    """
    Return a seasonal multiplier for *month_of_year* based on historical
    expense data.  1.0 = average; >1.0 = historically expensive month.
    """
    by_month: dict[int, list[float]] = defaultdict(list)
    for d in month_data:
        by_month[d["month"]].append(d["expenses"])

    all_exp = [d["expenses"] for d in month_data if d["expenses"] > 0]
    if not all_exp:
        return 1.0
    overall_avg = statistics.mean(all_exp)
    if overall_avg == 0:
        return 1.0

    month_vals = by_month.get(month_of_year, [])
    if not month_vals:
        return 1.0
    month_avg = statistics.mean(month_vals)
    return round(month_avg / overall_avg, 3)


def _confidence(months_of_data: int, has_income: bool) -> str:
    if months_of_data >= _MIN_MONTHS_HIGH_CONF and has_income:
        return "high"
    if months_of_data >= _MIN_MONTHS_MED_CONF:
        return "medium"
    return "low"


# ── Public API ────────────────────────────────────────────────────────────────

def forecast_cashflow(
    uid: int,
    horizon_months: int = 6,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Forecast monthly cash flow for the next *horizon_months* months.

    Returns:
        forecasts        — list of monthly forecasted states
        irregular_months — months identified as containing irregular expenses
        upcoming_bills   — dict {YYYY-MM: total_bill_obligations}
        confidence       — overall confidence: high | medium | low
        data_months_used — months of history used
        summary          — {avg_projected_income, avg_projected_expenses,
                            avg_projected_net, positive_months, negative_months}
        generated_at     — ISO timestamp
    """
    from datetime import datetime

    if anchor is None:
        anchor = date.today()
    horizon_months = max(1, min(horizon_months, 24))

    # Gather history
    history = _monthly_totals(uid, _HISTORY_MONTHS, anchor)
    months_with_data = sum(1 for h in history if h["income"] > 0 or h["expenses"] > 0)

    # Detect irregular months (one-off expense spikes)
    expense_vals = [h["expenses"] for h in history if h["expenses"] > 0]
    clean_expenses = _remove_outliers(expense_vals)
    irregular_months = []
    if expense_vals and clean_expenses:
        threshold = max(clean_expenses) * 1.3
        for h in history:
            if h["expenses"] > threshold:
                irregular_months.append(f"{h['year']:04d}-{h['month']:02d}")

    # Baseline averages (excluding outlier months)
    clean_history = [
        h for h in history
        if f"{h['year']:04d}-{h['month']:02d}" not in irregular_months
    ]
    if clean_history:
        avg_income   = statistics.mean(h["income"]   for h in clean_history)
        avg_expenses = statistics.mean(h["expenses"] for h in clean_history)
        income_std   = statistics.stdev([h["income"]   for h in clean_history]) if len(clean_history) > 1 else 0
        expense_std  = statistics.stdev([h["expenses"] for h in clean_history]) if len(clean_history) > 1 else 0
    else:
        avg_income = avg_expenses = income_std = expense_std = 0.0

    # Bills lookup
    bills_by_month = _upcoming_bills(uid, anchor, horizon_months)

    # Project forward
    forecasts: list[dict] = []
    y, m = anchor.year, anchor.month
    # Advance to next month (we forecast future, not current)
    m += 1
    if m > 12:
        m = 1
        y += 1

    for _ in range(horizon_months):
        label = f"{y:04d}-{m:02d}"
        seasonal = _seasonal_index(history, m)

        proj_income   = round(avg_income, 2)
        proj_expenses = round(avg_expenses * seasonal, 2)

        # Add known bill obligations
        bill_obligation = bills_by_month.get(label, 0.0)
        proj_expenses_with_bills = round(proj_expenses + bill_obligation, 2)

        net = round(proj_income - proj_expenses_with_bills, 2)

        # Confidence bounds (±1 std dev)
        income_lo   = round(max(0, proj_income   - income_std),   2)
        income_hi   = round(proj_income   + income_std,            2)
        expense_lo  = round(max(0, proj_expenses - expense_std),   2)
        expense_hi  = round(proj_expenses + expense_std,           2)

        forecasts.append({
            "month":                  label,
            "projected_income":       proj_income,
            "projected_expenses":     proj_expenses_with_bills,
            "bill_obligations":       round(bill_obligation, 2),
            "projected_net":          net,
            "seasonal_index":         seasonal,
            "income_range":           {"low": income_lo,  "high": income_hi},
            "expense_range":          {"low": expense_lo, "high": expense_hi},
            "likely_tight":           net < 0,
        })

        m += 1
        if m > 12:
            m = 1
            y += 1

    # Summary
    nets = [f["projected_net"] for f in forecasts]
    pos  = sum(1 for n in nets if n >= 0)
    neg  = horizon_months - pos

    overall_confidence = _confidence(months_with_data, avg_income > 0)

    logger.info(
        "Cash flow forecast uid=%s horizon=%d confidence=%s irregular=%d",
        uid, horizon_months, overall_confidence, len(irregular_months),
    )

    return {
        "forecasts":         forecasts,
        "irregular_months":  irregular_months,
        "upcoming_bills":    bills_by_month,
        "confidence":        overall_confidence,
        "data_months_used":  months_with_data,
        "summary": {
            "avg_projected_income":   round(avg_income, 2),
            "avg_projected_expenses": round(avg_expenses, 2),
            "avg_projected_net":      round(avg_income - avg_expenses, 2),
            "positive_months":        pos,
            "negative_months":        neg,
        },
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
