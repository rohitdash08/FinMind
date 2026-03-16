"""Savings opportunity detection service (#119).

Analyses a user's expense history to surface actionable savings opportunities:

1. **Consistent underspend** – categories where the user spends significantly
   less than their own 3-month average (i.e., they already proved they can
   spend less; they could budget lower and save the surplus).

2. **Top spender categories** – the highest-cost categories relative to total
   spend, flagged as potential candidates for reduction.

3. **Recurring / subscription detection** – same-amount expenses repeating
   ≥2 times in different months → possible subscription worth reviewing.

4. **Irregular big spends** – one-off large expenses (> 2× the category mean)
   that are not recurring, annotated so the user knows to plan for them.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func

from ..extensions import db
from ..models import Category, Expense

# ── helpers ────────────────────────────────────────────────────────────────────

_MONTHS = 3  # look-back window for trend analysis


def _month_label(d: date) -> str:
    return d.strftime("%Y-%m")


def _months_back(n: int) -> date:
    today = date.today()
    # approximate: subtract ~30 days per month
    return today - timedelta(days=30 * n)


def _category_monthly_spend(user_id: int, months: int) -> dict[int, dict[str, float]]:
    """Returns {category_id: {YYYY-MM: total_spent}}."""
    since = _months_back(months + 1)
    rows = (
        db.session.query(
            Expense.category_id,
            func.strftime("%Y-%m", Expense.spent_at).label("month"),
            func.sum(Expense.amount).label("total"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.category_id.isnot(None),
            Expense.expense_type != "INCOME",
            Expense.spent_at >= since,
        )
        .group_by(Expense.category_id, "month")
        .all()
    )
    result: dict[int, dict[str, float]] = defaultdict(dict)
    for cat_id, month, total in rows:
        result[cat_id][month] = float(total)
    return result


def _category_name(cat_id: int) -> str:
    cat = Category.query.get(cat_id)
    return cat.name if cat else f"Category #{cat_id}"


# ── opportunity detectors ──────────────────────────────────────────────────────


def _consistent_underspend(monthly: dict[int, dict[str, float]]) -> list[dict]:
    """Categories where recent spending is ≥ 20% below their own 3-month average."""
    today_month = _month_label(date.today())
    opportunities = []
    for cat_id, months in monthly.items():
        sorted_months = sorted(months.keys())
        if len(sorted_months) < 2:
            continue

        # Past months (exclude current month)
        past = [months[m] for m in sorted_months if m < today_month]
        current = months.get(today_month)

        if not past:
            continue

        avg_past = sum(past) / len(past)
        if avg_past == 0:
            continue

        # Use the last full past month as "recent"
        recent = past[-1]
        reduction_pct = round((1 - recent / avg_past) * 100, 1)

        if reduction_pct >= 20:
            # Potential monthly saving = difference vs average
            monthly_saving = round(avg_past - recent, 2)
            opportunities.append(
                {
                    "type": "consistent_underspend",
                    "category_id": cat_id,
                    "category_name": _category_name(cat_id),
                    "avg_monthly_spend": round(avg_past, 2),
                    "recent_spend": round(recent, 2),
                    "reduction_pct": reduction_pct,
                    "estimated_monthly_saving": monthly_saving,
                    "message": (
                        f"You reduced spending on {_category_name(cat_id)} by "
                        f"{reduction_pct}% recently. Locking in this lower budget "
                        f"could save ₹{monthly_saving:,.0f}/month."
                    ),
                }
            )
    return sorted(opportunities, key=lambda x: -x["estimated_monthly_saving"])


def _top_spender_categories(
    monthly: dict[int, dict[str, float]], top_n: int = 5
) -> list[dict]:
    """Top-N categories by average monthly spend."""
    totals: dict[int, float] = {}
    for cat_id, months in monthly.items():
        avg = sum(months.values()) / max(len(months), 1)
        totals[cat_id] = avg

    ranked = sorted(totals.items(), key=lambda x: -x[1])[:top_n]
    grand_total = sum(totals.values()) or 1

    result = []
    for cat_id, avg in ranked:
        pct_of_total = round(avg / grand_total * 100, 1)
        result.append(
            {
                "type": "top_spender",
                "category_id": cat_id,
                "category_name": _category_name(cat_id),
                "avg_monthly_spend": round(avg, 2),
                "pct_of_total_spend": pct_of_total,
                "message": (
                    f"{_category_name(cat_id)} accounts for {pct_of_total}% of "
                    "your monthly spend. Even a 10% reduction here would have a "
                    f"notable impact (≈₹{avg * 0.1:,.0f}/month)."
                ),
            }
        )
    return result


def _detect_subscriptions(user_id: int, months: int = 3) -> list[dict]:
    """Same-amount expenses appearing ≥ 2 times across different months."""
    since = _months_back(months + 1)
    rows = (
        db.session.query(
            Expense.category_id,
            Expense.amount,
            func.strftime("%Y-%m", Expense.spent_at).label("month"),
            func.count(Expense.id).label("cnt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.category_id.isnot(None),
            Expense.expense_type != "INCOME",
            Expense.spent_at >= since,
        )
        .group_by(Expense.category_id, Expense.amount, "month")
        .all()
    )

    # Build: {(cat_id, amount): set_of_months_where_it_appeared}
    tracker: dict[tuple, set] = defaultdict(set)
    for cat_id, amount, month, _cnt in rows:
        tracker[(cat_id, float(amount))].add(month)

    results = []
    seen_cats: set[int] = set()
    for (cat_id, amount), month_set in tracker.items():
        if len(month_set) >= 2 and cat_id not in seen_cats:
            seen_cats.add(cat_id)
            annual = round(amount * 12, 2)
            results.append(
                {
                    "type": "recurring_subscription",
                    "category_id": cat_id,
                    "category_name": _category_name(cat_id),
                    "recurring_amount": round(amount, 2),
                    "months_detected": sorted(month_set),
                    "estimated_annual_cost": annual,
                    "message": (
                        f"Possible recurring charge of ₹{amount:,.2f} detected in "
                        f"{_category_name(cat_id)}. Annual cost: ₹{annual:,.0f}. "
                        "Review if this subscription is still needed."
                    ),
                }
            )
    return sorted(results, key=lambda x: -x["estimated_annual_cost"])


def _irregular_big_spends(user_id: int, months: int = 3) -> list[dict]:
    """Single expenses that are ≥ 2× the category average."""
    since = _months_back(months + 1)

    # Get avg per category
    avgs = (
        db.session.query(
            Expense.category_id,
            func.avg(Expense.amount).label("avg_amt"),
        )
        .filter(
            Expense.user_id == user_id,
            Expense.category_id.isnot(None),
            Expense.expense_type != "INCOME",
            Expense.spent_at >= since,
        )
        .group_by(Expense.category_id)
        .all()
    )
    avg_map = {r.category_id: float(r.avg_amt) for r in avgs}

    # Find individual expenses > 2× category avg
    big = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == user_id,
            Expense.category_id.isnot(None),
            Expense.expense_type != "INCOME",
            Expense.spent_at >= since,
        )
        .all()
    )

    results = []
    seen_cats: set[int] = set()
    for e in big:
        avg = avg_map.get(e.category_id, 0)
        if avg > 0 and float(e.amount) > 2 * avg and e.category_id not in seen_cats:
            seen_cats.add(e.category_id)
            results.append(
                {
                    "type": "irregular_big_spend",
                    "category_id": e.category_id,
                    "category_name": _category_name(e.category_id),
                    "amount": float(e.amount),
                    "category_avg": round(avg, 2),
                    "spent_at": e.spent_at.isoformat(),
                    "notes": e.notes,
                    "message": (
                        f"Unusually large spend of ₹{float(e.amount):,.2f} in "
                        f"{_category_name(e.category_id)} on {e.spent_at} "
                        f"(avg: ₹{avg:,.2f}). Plan for this or find a cheaper alternative."
                    ),
                }
            )
    return sorted(results, key=lambda x: -x["amount"])


# ── public API ─────────────────────────────────────────────────────────────────


def detect_savings_opportunities(user_id: int, months: int = _MONTHS) -> dict:
    """Run all detectors and return a consolidated savings report."""
    monthly = _category_monthly_spend(user_id, months)

    underspend = _consistent_underspend(monthly)
    top_spend = _top_spender_categories(monthly)
    subscriptions = _detect_subscriptions(user_id, months)
    irregular = _irregular_big_spends(user_id, months)

    # Total estimated monthly saving from underspend opportunities
    total_potential_saving = sum(o["estimated_monthly_saving"] for o in underspend)

    all_opportunities = underspend + subscriptions + irregular

    return {
        "months_analysed": months,
        "total_estimated_monthly_saving": round(total_potential_saving, 2),
        "opportunities": all_opportunities,
        "top_spender_categories": top_spend,
        "summary": {
            "consistent_underspend": len(underspend),
            "recurring_subscriptions": len(subscriptions),
            "irregular_big_spends": len(irregular),
            "total_opportunities": len(all_opportunities),
        },
    }
