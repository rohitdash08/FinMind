"""
Personal Financial Digital Twin Simulator (Issue #100).

Creates a simulation model of a user's financial future by:
- Building a baseline from actual historical data
- Projecting income, expenses, and savings month-by-month
- Modelling life-change events (salary raise, new expense, job loss, etc.)
- Detecting financial risks (runway exhaustion, negative savings rate)
- Generating a long-term savings outlook

No ML — deterministic compound-growth projections with event overrides.
Pure Python, no extra deps.

Public API
----------
run_digital_twin(uid, horizon_months, events, anchor) → DigitalTwinResult dict
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func

from ..extensions import db
from ..models import Expense

logger = logging.getLogger("finmind.digital_twin")

# ── Constants ─────────────────────────────────────────────────────────────────

# Default annual inflation / cost-of-living drift applied to expenses
_DEFAULT_EXPENSE_DRIFT_PA = 0.03   # 3 % per year → 0.25 % per month

# Default annual income growth (conservative)
_DEFAULT_INCOME_GROWTH_PA = 0.04   # 4 % per year

# Risk thresholds
_LOW_SAVINGS_RATE_THRESHOLD = 0.05   # below 5 % savings rate → warning
_NEG_RUNWAY_THRESHOLD       = 0     # months until savings = 0

# ── Helpers ───────────────────────────────────────────────────────────────────

def _iter_months_forward(anchor: date, n: int):
    """Yield (year, month) tuples starting from anchor for n months."""
    y, m = anchor.year, anchor.month
    for _ in range(n):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _month_label(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def _avg_monthly(uid: int, months_back: int, anchor: date) -> tuple[float, float]:
    """Return (avg_monthly_income, avg_monthly_expenses) for the last months_back months."""
    totals_i, totals_e = [], []
    y, m = anchor.year, anchor.month
    for _ in range(months_back):
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
        totals_i.append(inc)
        totals_e.append(exp)
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    months = max(months_back, 1)
    return round(sum(totals_i) / months, 2), round(sum(totals_e) / months, 2)


# ── Event processing ──────────────────────────────────────────────────────────

VALID_EVENT_TYPES = frozenset([
    "income_change",      # pct_change or amount_change on monthly income
    "expense_change",     # pct_change or amount_change on monthly expenses
    "one_time_expense",   # single large expense in a specific month
    "one_time_income",    # windfall / bonus
    "job_loss",           # income drops to 0
    "job_recovery",       # income restored to a given amount or % of baseline
])


def _apply_events(
    month_label: str,
    income: float,
    expenses: float,
    events: list[dict],
    baseline_income: float,
) -> tuple[float, float, list[str]]:
    """
    Apply all events scheduled for *month_label*.
    Returns (new_income, new_expenses, list_of_applied_event_labels).
    """
    applied = []
    for ev in events:
        if ev.get("month") != month_label:
            continue
        ev_type = ev.get("type", "")
        label   = ev.get("label") or ev_type

        if ev_type == "income_change":
            pct = ev.get("pct_change")
            amt = ev.get("amount_change")
            if pct is not None:
                income = max(0.0, income * (1 + float(pct) / 100))
            elif amt is not None:
                income = max(0.0, income + float(amt))
            applied.append(label)

        elif ev_type == "expense_change":
            pct = ev.get("pct_change")
            amt = ev.get("amount_change")
            if pct is not None:
                expenses = max(0.0, expenses * (1 + float(pct) / 100))
            elif amt is not None:
                expenses = max(0.0, expenses + float(amt))
            applied.append(label)

        elif ev_type == "one_time_expense":
            amt = float(ev.get("amount", 0))
            expenses += amt
            applied.append(f"{label} (+{amt:.0f})")

        elif ev_type == "one_time_income":
            amt = float(ev.get("amount", 0))
            income += amt
            applied.append(f"{label} (+{amt:.0f})")

        elif ev_type == "job_loss":
            income = 0.0
            applied.append(label)

        elif ev_type == "job_recovery":
            pct = ev.get("pct_of_baseline")
            amt = ev.get("amount")
            if pct is not None:
                income = baseline_income * float(pct) / 100
            elif amt is not None:
                income = float(amt)
            else:
                income = baseline_income
            applied.append(label)

    return round(income, 2), round(expenses, 2), applied


# ── Risk detection ────────────────────────────────────────────────────────────

def _detect_risks(projections: list[dict], current_savings: float) -> list[dict]:
    risks = []
    cumulative = current_savings

    for i, p in enumerate(projections):
        net = p["net_flow"]
        cumulative += net
        p["cumulative_savings"] = round(cumulative, 2)

        # Low savings rate
        if p["income"] > 0:
            sr = net / p["income"]
            if sr < _LOW_SAVINGS_RATE_THRESHOLD and net < 0:
                risks.append({
                    "month": p["month"],
                    "risk": "negative_net_flow",
                    "severity": "high",
                    "detail": f"Projected deficit of {abs(net):.2f} in {p['month']}.",
                })

        # Runway exhaustion
        if cumulative < 0 and (i == 0 or projections[i - 1].get("cumulative_savings", 1) >= 0):
            risks.append({
                "month": p["month"],
                "risk": "savings_exhausted",
                "severity": "high",
                "detail": f"Cumulative savings projected to go negative in {p['month']}.",
            })

    return risks


# ── Public API ────────────────────────────────────────────────────────────────

def run_digital_twin(
    uid: int,
    horizon_months: int = 12,
    events: list[dict] | None = None,
    anchor: date | None = None,
    baseline_months: int = 3,
) -> dict[str, Any]:
    """
    Run the personal financial digital twin simulation.

    Parameters
    ----------
    uid             : authenticated user id
    horizon_months  : how far to project (1–60)
    events          : list of life-change event dicts (see VALID_EVENT_TYPES)
    anchor          : start of the projection (defaults to today)
    baseline_months : months of history used to build the baseline

    Returns
    -------
    dict with keys:
        baseline          — {income, expenses, net_flow, savings_rate_pct}
        projections       — list of month-by-month projected states
        risks             — detected financial risk events
        summary           — {total_projected_savings, avg_monthly_net,
                             months_positive, months_negative, final_cumulative}
        horizon_months    — int
        events_applied    — count of events scheduled
        generated_at      — ISO timestamp
    """
    from datetime import datetime

    if anchor is None:
        anchor = date.today()
    horizon_months = max(1, min(horizon_months, 60))
    events = events or []

    # ── Build baseline ────────────────────────────────────────────────────────
    avg_income, avg_expenses = _avg_monthly(uid, baseline_months, anchor)
    baseline_net = round(avg_income - avg_expenses, 2)
    baseline_sr = round(baseline_net / avg_income * 100, 1) if avg_income > 0 else 0.0

    # Monthly drift rates
    income_drift   = _DEFAULT_INCOME_GROWTH_PA / 12
    expense_drift  = _DEFAULT_EXPENSE_DRIFT_PA / 12

    # ── Project month-by-month ────────────────────────────────────────────────
    cur_income   = avg_income
    cur_expenses = avg_expenses
    projections  = []
    events_applied_total = 0

    for i, (year, month) in enumerate(_iter_months_forward(anchor, horizon_months)):
        label = _month_label(year, month)

        # Apply natural drift
        cur_income   = round(cur_income   * (1 + income_drift), 2)
        cur_expenses = round(cur_expenses * (1 + expense_drift), 2)

        # Apply scheduled events
        new_income, new_expenses, applied_labels = _apply_events(
            label, cur_income, cur_expenses, events, avg_income
        )
        if applied_labels:
            events_applied_total += len(applied_labels)
            cur_income   = new_income
            cur_expenses = new_expenses

        net   = round(cur_income - cur_expenses, 2)
        sr    = round(net / cur_income * 100, 1) if cur_income > 0 else 0.0

        projections.append({
            "month":          label,
            "income":         cur_income,
            "expenses":       cur_expenses,
            "net_flow":       net,
            "savings_rate_pct": sr,
            "events_applied": applied_labels,
        })

    # ── Risk detection ────────────────────────────────────────────────────────
    risks = _detect_risks(projections, current_savings=0.0)

    # ── Summary ───────────────────────────────────────────────────────────────
    total_net      = sum(p["net_flow"] for p in projections)
    months_pos     = sum(1 for p in projections if p["net_flow"] >= 0)
    months_neg     = horizon_months - months_pos
    final_cum      = projections[-1].get("cumulative_savings", 0.0) if projections else 0.0
    avg_monthly_net = round(total_net / horizon_months, 2) if horizon_months else 0.0

    logger.info(
        "Digital twin uid=%s horizon=%d events=%d risks=%d",
        uid, horizon_months, events_applied_total, len(risks),
    )

    return {
        "baseline": {
            "income":            avg_income,
            "expenses":          avg_expenses,
            "net_flow":          baseline_net,
            "savings_rate_pct":  baseline_sr,
        },
        "projections": projections,
        "risks": risks,
        "summary": {
            "total_projected_savings": round(total_net, 2),
            "avg_monthly_net":         avg_monthly_net,
            "months_positive":         months_pos,
            "months_negative":         months_neg,
            "final_cumulative_savings": round(final_cum, 2),
        },
        "horizon_months":    horizon_months,
        "events_applied":    events_applied_total,
        "generated_at":      datetime.utcnow().isoformat() + "Z",
    }
