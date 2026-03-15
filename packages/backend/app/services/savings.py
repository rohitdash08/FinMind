"""Savings opportunity detection engine.

Analyses a user's expense history to surface concrete, actionable
saving opportunities across several dimensions:

1. **Spiking categories** – categories whose spend this month exceeds
   the 3-month average by more than 20 %.
2. **Duplicate recurring** – multiple recurring entries whose amounts
   are within 5 % of each other (possible duplicate subscriptions).
3. **Top-waste categories** – the 3 categories that consume the
   largest share of monthly spend.
4. **Trend alerts** – categories with a statistically increasing
   spend trend over the last 6 months (linear regression slope > 0).

Each opportunity includes an estimated monthly saving amount when
possible.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category, RecurringExpense, RecurringCadence

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Opportunity:
    type: str  # spiking_category | duplicate_recurring | top_spender | trend_increase
    title: str
    description: str
    estimated_monthly_saving: float = 0.0
    category: str | None = None
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _month_range(ref: date, months_back: int = 0):
    """Return (start_date, end_date) for a calendar month *months_back* ago."""
    year = ref.year + (ref.month - 1 - months_back) // 12
    month = (ref.month - 1 - months_back) % 12 + 1
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def _monthly_totals(user_id: int, months: int = 6) -> list[dict]:
    """Return list of {year_month, total, by_category} for the last *months* months."""
    today = date.today()
    results = []
    for i in range(months - 1, -1, -1):
        start, end = _month_range(today, i)
        rows = (
            db.session.query(Category.name, func.sum(Expense.amount))
            .join(Expense, Expense.category_id == Category.id)
            .filter(
                Expense.user_id == user_id,
                Expense.expense_type == "EXPENSE",
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .group_by(Category.name)
            .all()
        )
        by_cat = {name: float(total or 0) for name, total in rows}
        results.append(
            {
                "year_month": start.strftime("%Y-%m"),
                "total": sum(by_cat.values()),
                "by_category": by_cat,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_spiking_categories(monthly: list[dict]) -> list[Opportunity]:
    """Detect categories whose current-month spend is > 20% above their 3-month avg."""
    if len(monthly) < 4:
        return []
    current = monthly[-1]["by_category"]
    # average over the 3 preceding months
    prev = defaultdict(list)
    for m in monthly[-4:-1]:
        for cat, val in m["by_category"].items():
            prev[cat].append(val)

    opps: list[Opportunity] = []
    for cat, cur_val in current.items():
        hist = prev.get(cat)
        if not hist or cur_val <= 0:
            continue
        avg = sum(hist) / len(hist)
        if avg <= 0:
            continue
        pct_over = (cur_val - avg) / avg
        if pct_over > 0.20:
            saving = round(cur_val - avg, 2)
            opps.append(
                Opportunity(
                    type="spiking_category",
                    title=f"Spending spike in {cat}",
                    description=(
                        f"Your {cat} spending this month ({cur_val:.2f}) is "
                        f"{pct_over:.0%} above your 3-month average ({avg:.2f})."
                    ),
                    estimated_monthly_saving=saving,
                    category=cat,
                )
            )
    return opps


def _detect_duplicate_recurring(user_id: int) -> list[Opportunity]:
    """Find recurring expenses with very similar amounts (possible duplicates)."""
    active = (
        RecurringExpense.query.filter_by(user_id=user_id, active=True)
        .order_by(RecurringExpense.amount)
        .all()
    )
    opps: list[Opportunity] = []
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            if a.id == b.id:
                continue
            diff = abs(float(a.amount) - float(b.amount))
            base = max(float(a.amount), float(b.amount), 0.01)
            if diff / base <= 0.05:
                cat_a = a.category_id  # may be None
                opps.append(
                    Opportunity(
                        type="duplicate_recurring",
                        title=f"Possible duplicate recurring expense",
                        description=(
                            f"Two recurring expenses are within 5% of each other: "
                            f"'{a.notes}' ({a.amount}) and '{b.notes}' ({b.amount}). "
                            f"Consider merging or cancelling one."
                        ),
                        estimated_monthly_saving=round(min(float(a.amount), float(b.amount)), 2),
                        details={
                            "recurring_id_a": a.id,
                            "recurring_id_b": b.id,
                        },
                    )
                )
    return opps


def _detect_top_spenders(monthly: list[dict]) -> list[Opportunity]:
    """Surface the top-3 categories by spend as potential reduction targets."""
    if not monthly:
        return []
    current = monthly[-1]["by_category"]
    if not current:
        return []
    sorted_cats = sorted(current.items(), key=lambda x: x[1], reverse=True)
    opps: list[Opportunity] = []
    for cat, val in sorted_cats[:3]:
        if val <= 0:
            continue
        # saving target: 10% reduction
        target = round(val * 0.10, 2)
        opps.append(
            Opportunity(
                type="top_spender",
                title=f"Reduce {cat} spending",
                description=(
                    f"{cat} accounts for {val:.2f} of your spending this month. "
                    f"A 10% reduction would save {target:.2f}."
                ),
                estimated_monthly_saving=target,
                category=cat,
            )
        )
    return opps


def _detect_increasing_trends(monthly: list[dict]) -> list[Opportunity]:
    """Use simple linear regression to find categories with a clear upward trend."""
    if len(monthly) < 4:
        return []
    # Collect category time-series
    all_cats: set[str] = set()
    for m in monthly:
        all_cats.update(m["by_category"].keys())

    opps: list[Opportunity] = []
    n = len(monthly)
    xs = list(range(n))

    for cat in all_cats:
        ys = [m["by_category"].get(cat, 0.0) for m in monthly]
        if all(y == 0 for y in ys):
            continue
        # simple OLS slope
        x_mean = sum(xs) / n
        y_mean = sum(ys) / n
        num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
        den = sum((x - x_mean) ** 2 for x in xs)
        if den == 0:
            continue
        slope = num / den
        if slope > 0 and y_mean > 0:
            projected_next = ys[-1] + slope
            saving = round(max(projected_next - y_mean, 0), 2)
            opps.append(
                Opportunity(
                    type="trend_increase",
                    title=f"Increasing trend in {cat}",
                    description=(
                        f"Your {cat} spending has been trending upward at "
                        f"{slope:.2f}/month over the last {n} months."
                    ),
                    estimated_monthly_saving=saving,
                    category=cat,
                )
            )
    return opps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_savings_opportunities(user_id: int) -> dict:
    """Run all detectors and return a structured response."""
    monthly = _monthly_totals(user_id, months=6)
    opps: list[Opportunity] = []
    opps.extend(_detect_spiking_categories(monthly))
    opps.extend(_detect_duplicate_recurring(user_id))
    opps.extend(_detect_top_spenders(monthly))
    opps.extend(_detect_increasing_trends(monthly))

    total_estimated = sum(o.estimated_monthly_saving for o in opps)

    result = {
        "opportunities": [asdict(o) for o in opps],
        "total_estimated_monthly_saving": round(total_estimated, 2),
        "opportunity_count": len(opps),
        "analysis_months": len(monthly),
    }
    logger.info(
        "Savings scan user=%s found=%s total_est=%.2f",
        user_id,
        len(opps),
        total_estimated,
    )
    return result
