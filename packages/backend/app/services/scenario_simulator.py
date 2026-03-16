"""
Financial Scenario Simulator — What-If Planning (Issue #94).

Allows users to simulate the financial impact of prospective decisions
without mutating any real data:

  • reduce / increase a spending category by a percentage or fixed amount
  • apply a salary / income change
  • model a rent or fixed-cost change
  • combine multiple adjustments in a single simulation

All calculations are performed in-memory against the user's *current* monthly
average; nothing is written to the database.

Public API
----------
run_scenario(uid, adjustments, months, anchor) → ScenarioResult dict
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.scenario")

# ── Types & constants ─────────────────────────────────────────────────────────

ADJUSTMENT_TYPES = frozenset(
    ["category_change", "income_change", "fixed_cost_change"]
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _avg_monthly_income(uid: int, months: int, anchor: date) -> float:
    totals = []
    y, m = anchor.year, anchor.month
    for _ in range(months):
        val = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "INCOME",
            )
            .scalar()
        )
        totals.append(float(val or 0))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return round(sum(totals) / months, 2) if months else 0.0


def _avg_monthly_category_spend(uid: int, months: int, anchor: date) -> dict[str, float]:
    """Return {category_id_str: avg_monthly_amount} over last *months* months."""
    combined: dict[str | None, list[float]] = {}
    y, m = anchor.year, anchor.month
    for _ in range(months):
        rows = (
            db.session.query(
                Expense.category_id,
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
            )
            .filter(
                Expense.user_id == uid,
                extract("year", Expense.spent_at) == y,
                extract("month", Expense.spent_at) == m,
                Expense.expense_type == "EXPENSE",
            )
            .group_by(Expense.category_id)
            .all()
        )
        for row in rows:
            key = str(row.category_id) if row.category_id is not None else "uncat"
            combined.setdefault(key, []).append(float(row.total))
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    return {
        k: round(sum(v) / months, 2)
        for k, v in combined.items()
    }


def _category_name(cat_id: int | None) -> str:
    if cat_id is None:
        return "Uncategorized"
    cat = db.session.get(Category, cat_id)
    return cat.name if cat else f"Category {cat_id}"


def _apply_adjustment(
    baseline_expenses: dict[str, float],
    baseline_income: float,
    adj: dict,
) -> tuple[dict[str, float], float, str | None]:
    """
    Apply a single adjustment to (baseline_expenses, baseline_income).

    Returns (new_expenses, new_income, error_message).
    error_message is None on success.
    """
    adj_type = adj.get("type")
    if adj_type not in ADJUSTMENT_TYPES:
        return baseline_expenses, baseline_income, (
            f"unknown adjustment type '{adj_type}'; "
            f"must be one of {sorted(ADJUSTMENT_TYPES)}"
        )

    new_expenses = dict(baseline_expenses)
    new_income = baseline_income

    if adj_type == "category_change":
        # Required: category_id (str/int) or "uncat"
        # One of: pct_change (float, e.g. -10 = −10%) or amount_change (float)
        cat_key = str(adj.get("category_id", "uncat"))
        pct = adj.get("pct_change")
        fixed = adj.get("amount_change")

        if pct is None and fixed is None:
            return baseline_expenses, baseline_income, (
                "category_change requires 'pct_change' or 'amount_change'"
            )

        current = new_expenses.get(cat_key, 0.0)
        if pct is not None:
            delta = current * float(pct) / 100
        else:
            delta = float(fixed)
        new_val = max(0.0, current + delta)
        new_expenses[cat_key] = round(new_val, 2)

    elif adj_type == "income_change":
        pct = adj.get("pct_change")
        fixed = adj.get("amount_change")
        if pct is None and fixed is None:
            return baseline_expenses, baseline_income, (
                "income_change requires 'pct_change' or 'amount_change'"
            )
        if pct is not None:
            new_income = round(max(0.0, baseline_income * (1 + float(pct) / 100)), 2)
        else:
            new_income = round(max(0.0, baseline_income + float(fixed)), 2)

    elif adj_type == "fixed_cost_change":
        # Model a rent / subscription / loan change as an unnamed fixed entry
        # stored under a synthetic key "fixed:<label>"
        label = str(adj.get("label", "fixed_cost"))
        key = f"fixed:{label}"
        pct = adj.get("pct_change")
        fixed = adj.get("amount_change")
        if pct is None and fixed is None:
            return baseline_expenses, baseline_income, (
                "fixed_cost_change requires 'pct_change' or 'amount_change'"
            )
        current = new_expenses.get(key, 0.0)
        if pct is not None:
            delta = current * float(pct) / 100
        else:
            delta = float(fixed)
        new_val = max(0.0, current + delta)
        new_expenses[key] = round(new_val, 2)

    return new_expenses, new_income, None


# ── Public API ────────────────────────────────────────────────────────────────


def run_scenario(
    uid: int,
    adjustments: list[dict],
    months: int = 3,
    anchor: date | None = None,
) -> dict[str, Any]:
    """
    Simulate the financial impact of *adjustments* against the user's
    current average monthly spending.

    Parameters
    ----------
    uid         : authenticated user id
    adjustments : list of adjustment dicts (see ADJUSTMENT_TYPES)
    months      : look-back window for computing the baseline (1–12)
    anchor      : end month for the baseline window (defaults to today)

    Returns
    -------
    dict with keys:
        baseline           — current avg monthly snapshot
        scenario           — projected snapshot after adjustments
        delta              — per-field difference (scenario − baseline)
        applied_adjustments — list of successfully applied adjustments
        errors             — list of validation errors (empty if all OK)
        analysis_months    — months used for baseline
        generated_at       — ISO timestamp
    """
    from datetime import datetime

    if anchor is None:
        anchor = date.today()
    months = max(1, min(months, 12))

    # ── Build baseline ────────────────────────────────────────────────────────
    baseline_cat = _avg_monthly_category_spend(uid, months, anchor)
    baseline_income = _avg_monthly_income(uid, months, anchor)
    baseline_expenses = sum(baseline_cat.values())
    baseline_net = round(baseline_income - baseline_expenses, 2)

    # ── Apply adjustments ─────────────────────────────────────────────────────
    current_cats = dict(baseline_cat)
    current_income = baseline_income
    applied: list[dict] = []
    errors: list[str] = []

    for adj in adjustments:
        new_cats, new_income, err = _apply_adjustment(current_cats, current_income, adj)
        if err:
            errors.append(err)
        else:
            label = adj.get("label") or adj.get("type", "adjustment")
            applied.append({**adj, "_label": label})
            current_cats = new_cats
            current_income = new_income

    scenario_expenses = sum(current_cats.values())
    scenario_net = round(current_income - scenario_expenses, 2)

    # ── Resolve category names for readable output ────────────────────────────
    def _enrich_cats(raw: dict[str, float]) -> list[dict]:
        result = []
        for key, amount in sorted(raw.items(), key=lambda x: -x[1]):
            if key.startswith("fixed:"):
                name = key[6:] + " (fixed cost)"
                cat_id = None
            elif key == "uncat":
                name = "Uncategorized"
                cat_id = None
            else:
                try:
                    cat_id = int(key)
                except ValueError:
                    cat_id = None
                name = _category_name(cat_id)
            result.append({"category_id": key, "category_name": name, "amount": round(amount, 2)})
        return result

    baseline_cats_out = _enrich_cats(baseline_cat)
    scenario_cats_out = _enrich_cats(current_cats)

    delta_expenses = round(scenario_expenses - baseline_expenses, 2)
    delta_income = round(current_income - baseline_income, 2)
    delta_net = round(scenario_net - baseline_net, 2)

    # Savings rate (% of income saved)
    def _savings_rate(income: float, expenses: float) -> float | None:
        if income <= 0:
            return None
        return round((income - expenses) / income * 100, 1)

    logger.info(
        "Scenario simulation uid=%s adjustments=%d baseline_net=%s scenario_net=%s",
        uid, len(adjustments), baseline_net, scenario_net,
    )

    return {
        "baseline": {
            "income": baseline_income,
            "expenses": round(baseline_expenses, 2),
            "net_flow": baseline_net,
            "savings_rate_pct": _savings_rate(baseline_income, baseline_expenses),
            "categories": baseline_cats_out,
        },
        "scenario": {
            "income": current_income,
            "expenses": round(scenario_expenses, 2),
            "net_flow": scenario_net,
            "savings_rate_pct": _savings_rate(current_income, scenario_expenses),
            "categories": scenario_cats_out,
        },
        "delta": {
            "income": delta_income,
            "expenses": delta_expenses,
            "net_flow": delta_net,
            "net_flow_direction": "better" if delta_net > 0 else ("worse" if delta_net < 0 else "unchanged"),
        },
        "applied_adjustments": applied,
        "errors": errors,
        "analysis_months": months,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
