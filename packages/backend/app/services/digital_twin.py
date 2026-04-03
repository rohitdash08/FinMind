from __future__ import annotations

"""
Personal Financial Digital Twin Simulator (Issue #100)

A Digital Twin is a living, queryable model of the user's financial life.
It aggregates all data sources (expenses, income, bills, budgets, forecasts)
into a unified snapshot and provides forward projections via Monte Carlo
simulation and deterministic modeling.

Core capabilities:
  - Snapshot: full state of the user's finances at a point in time
  - Project: forward simulation (deterministic + stochastic MC)
  - Stress test: apply economic shocks (job loss, medical emergency, market crash)
  - Goal tracking: retirement, emergency fund, debt freedom, house purchase
  - Advice engine: ranked next-best-action recommendations
"""

import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.models import db, Expense, Income, RecurringBill, Budget, Saving


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class FinancialSnapshot:
    uid: int
    snapshot_date: date
    monthly_income: float
    monthly_expenses: float
    monthly_surplus: float
    savings_balance: float
    total_recurring_bills: float
    active_bills_count: int
    overdue_bills_count: int
    savings_rate_pct: float
    top_expense_categories: list[dict]
    health_score: float | None = None
    goals: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "uid": self.uid,
            "snapshot_date": self.snapshot_date.isoformat(),
            "monthly_income": round(self.monthly_income, 2),
            "monthly_expenses": round(self.monthly_expenses, 2),
            "monthly_surplus": round(self.monthly_surplus, 2),
            "savings_balance": round(self.savings_balance, 2),
            "total_recurring_bills": round(self.total_recurring_bills, 2),
            "active_bills_count": self.active_bills_count,
            "overdue_bills_count": self.overdue_bills_count,
            "savings_rate_pct": round(self.savings_rate_pct, 1),
            "top_expense_categories": self.top_expense_categories,
            "health_score": self.health_score,
            "goals": self.goals,
        }


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------

def _avg_monthly_amount(uid: int, model, date_field: str, amount_field: str, months: int = 3) -> float:
    cutoff = date.today() - timedelta(days=30 * months)
    rows = db.session.query(model).filter(
        getattr(model, "user_id") == uid,
        getattr(model, date_field) >= cutoff,
    ).all()
    if not rows:
        return 0.0
    return sum(float(getattr(r, amount_field) or 0) for r in rows) / months


def _savings_balance(uid: int) -> float:
    try:
        savings = db.session.query(Saving).filter_by(user_id=uid).all()
        return sum(float(s.amount or 0) for s in savings)
    except Exception:
        return 0.0


def _top_expense_categories(uid: int, months: int = 3, top_n: int = 5) -> list[dict]:
    cutoff = date.today() - timedelta(days=30 * months)
    expenses = db.session.query(Expense).filter(
        Expense.user_id == uid, Expense.date >= cutoff
    ).all()
    totals: dict[int, float] = {}
    for e in expenses:
        cat = e.category_id or 0
        totals[cat] = totals.get(cat, 0.0) + float(e.amount or 0)
    sorted_cats = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        {"category_id": cat_id, "monthly_avg": round(total / months, 2)}
        for cat_id, total in sorted_cats
    ]


def _bills_summary(uid: int) -> tuple[float, int, int]:
    """Return (total_monthly, active_count, overdue_count)."""
    bills = db.session.query(RecurringBill).filter_by(user_id=uid).all()
    today = date.today()
    total = 0.0
    active = 0
    overdue = 0
    for b in bills:
        is_active = getattr(b, "active", True)
        if not is_active:
            continue
        active += 1
        amount = float(getattr(b, "amount", 0) or 0)
        total += amount
        due = getattr(b, "due_date", None)
        paid = getattr(b, "is_paid", False)
        if due and not paid and (isinstance(due, date) and due < today):
            overdue += 1
    return total, active, overdue


def build_snapshot(uid: int, months: int = 3) -> FinancialSnapshot:
    """Build a current financial snapshot for the user."""
    monthly_income = _avg_monthly_amount(uid, Income, "date", "amount", months)
    monthly_expenses = _avg_monthly_amount(uid, Expense, "date", "amount", months)
    monthly_surplus = monthly_income - monthly_expenses
    savings = _savings_balance(uid)
    bills_total, bills_active, bills_overdue = _bills_summary(uid)
    savings_rate = (monthly_surplus / monthly_income * 100) if monthly_income > 0 else 0.0
    top_cats = _top_expense_categories(uid, months)

    return FinancialSnapshot(
        uid=uid,
        snapshot_date=date.today(),
        monthly_income=monthly_income,
        monthly_expenses=monthly_expenses,
        monthly_surplus=monthly_surplus,
        savings_balance=savings,
        total_recurring_bills=bills_total,
        active_bills_count=bills_active,
        overdue_bills_count=bills_overdue,
        savings_rate_pct=savings_rate,
        top_expense_categories=top_cats,
    )


# ---------------------------------------------------------------------------
# Projection engine
# ---------------------------------------------------------------------------

def project_deterministic(snapshot: FinancialSnapshot, months: int = 24) -> list[dict]:
    """Simple deterministic month-by-month projection."""
    projection = []
    balance = snapshot.savings_balance
    for i in range(1, months + 1):
        balance += snapshot.monthly_surplus
        projection.append({
            "month": i,
            "month_label": _month_label(i),
            "income": round(snapshot.monthly_income, 2),
            "expenses": round(snapshot.monthly_expenses, 2),
            "net": round(snapshot.monthly_surplus, 2),
            "cumulative_savings": round(balance, 2),
        })
    return projection


def _month_label(offset: int) -> str:
    d = date.today().replace(day=1)
    month = d.month + offset - 1
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    return f"{year}-{month:02d}"


def project_monte_carlo(
    snapshot: FinancialSnapshot,
    months: int = 24,
    simulations: int = 500,
    income_volatility: float = 0.05,
    expense_volatility: float = 0.08,
) -> dict:
    """
    Monte Carlo simulation returning percentile bands.
    income_volatility / expense_volatility: std deviation as fraction of mean.
    """
    all_balances: list[list[float]] = []
    for _ in range(simulations):
        balance = snapshot.savings_balance
        run = []
        for _ in range(months):
            inc = max(0.0, random.gauss(snapshot.monthly_income, snapshot.monthly_income * income_volatility))
            exp = max(0.0, random.gauss(snapshot.monthly_expenses, snapshot.monthly_expenses * expense_volatility))
            balance += inc - exp
            run.append(balance)
        all_balances.append(run)

    percentiles = []
    for m in range(months):
        month_vals = sorted(run[m] for run in all_balances)
        n = len(month_vals)
        percentiles.append({
            "month": m + 1,
            "month_label": _month_label(m + 1),
            "p10": round(month_vals[int(n * 0.10)], 2),
            "p25": round(month_vals[int(n * 0.25)], 2),
            "p50": round(month_vals[int(n * 0.50)], 2),
            "p75": round(month_vals[int(n * 0.75)], 2),
            "p90": round(month_vals[int(n * 0.90)], 2),
        })

    return {
        "simulations": simulations,
        "months": months,
        "income_volatility_pct": income_volatility * 100,
        "expense_volatility_pct": expense_volatility * 100,
        "projection": percentiles,
    }


# ---------------------------------------------------------------------------
# Stress testing
# ---------------------------------------------------------------------------

_STRESS_PRESETS = {
    "job_loss": {"income_shock_pct": -100, "expense_shock_pct": -20, "duration_months": 6},
    "medical_emergency": {"one_time_expense": 10000, "expense_shock_pct": 20, "duration_months": 3},
    "market_crash": {"savings_shock_pct": -30, "expense_shock_pct": 10, "duration_months": 12},
    "pay_cut_20": {"income_shock_pct": -20, "duration_months": 12},
    "rent_spike_40": {"expense_shock_pct": 15, "duration_months": 24},
}


def stress_test(snapshot: FinancialSnapshot, scenario: str | dict, months: int = 24) -> dict:
    """Apply an economic shock and project the outcome."""
    if isinstance(scenario, str):
        params = _STRESS_PRESETS.get(scenario)
        if params is None:
            raise ValueError(f"Unknown preset: {scenario!r}. Valid: {list(_STRESS_PRESETS)}")
        label = scenario
    else:
        params = scenario
        label = "custom"

    income_shock = params.get("income_shock_pct", 0) / 100.0
    expense_shock = params.get("expense_shock_pct", 0) / 100.0
    savings_shock = params.get("savings_shock_pct", 0) / 100.0
    one_time = params.get("one_time_expense", 0)
    shock_duration = params.get("duration_months", months)

    balance = snapshot.savings_balance * (1 + savings_shock)
    projection = []
    for i in range(1, months + 1):
        in_shock = i <= shock_duration
        income = snapshot.monthly_income * (1 + income_shock if in_shock else 1.0)
        expenses = snapshot.monthly_expenses * (1 + expense_shock if in_shock else 1.0)
        if i == 1:
            expenses += one_time
        balance += income - expenses
        projection.append({
            "month": i,
            "month_label": _month_label(i),
            "income": round(income, 2),
            "expenses": round(expenses, 2),
            "net": round(income - expenses, 2),
            "cumulative_savings": round(balance, 2),
            "in_shock_period": in_shock,
        })

    # Find month when savings go negative
    broke_month = next((p["month"] for p in projection if p["cumulative_savings"] < 0), None)
    return {
        "scenario": label,
        "params": params,
        "months_until_insolvency": broke_month,
        "projection": projection,
    }


# ---------------------------------------------------------------------------
# Goal tracking
# ---------------------------------------------------------------------------

def track_goals(snapshot: FinancialSnapshot, goals: list[dict]) -> list[dict]:
    """
    Evaluate progress toward financial goals.
    Each goal: {type, target_amount, current_amount?, label?}
    Types: emergency_fund, retirement, house_purchase, debt_freedom, custom
    """
    results = []
    surplus = snapshot.monthly_surplus

    for goal in goals:
        g_type = goal.get("type", "custom")
        label = goal.get("label", g_type)
        target = float(goal.get("target_amount", 0))
        current = float(goal.get("current_amount", snapshot.savings_balance))

        remaining = max(0.0, target - current)
        months_to_goal = math.ceil(remaining / surplus) if surplus > 0 else None
        progress_pct = min(100.0, current / target * 100) if target > 0 else 0.0

        results.append({
            "type": g_type,
            "label": label,
            "target_amount": round(target, 2),
            "current_amount": round(current, 2),
            "remaining": round(remaining, 2),
            "progress_pct": round(progress_pct, 1),
            "months_to_goal": months_to_goal,
            "achievable": months_to_goal is not None,
            "on_track": progress_pct >= 50,
        })

    return results


# ---------------------------------------------------------------------------
# Advice engine
# ---------------------------------------------------------------------------

def generate_recommendations(snapshot: FinancialSnapshot) -> list[dict]:
    """Return prioritized next-best-action recommendations."""
    recs = []

    if snapshot.overdue_bills_count > 0:
        recs.append({
            "priority": 1,
            "action": "pay_overdue_bills",
            "title": f"Pay {snapshot.overdue_bills_count} overdue bill(s)",
            "impact": "high",
            "detail": "Overdue bills may incur late fees and damage credit score.",
        })

    if snapshot.savings_rate_pct < 10:
        recs.append({
            "priority": 2,
            "action": "increase_savings_rate",
            "title": "Savings rate below 10%",
            "impact": "high",
            "detail": f"Current savings rate is {snapshot.savings_rate_pct:.1f}%. Target 20%.",
        })

    if snapshot.savings_balance < snapshot.monthly_expenses * 3:
        recs.append({
            "priority": 3,
            "action": "build_emergency_fund",
            "title": "Emergency fund below 3 months of expenses",
            "impact": "high",
            "detail": "Build a 3-6 month emergency fund as a financial cushion.",
        })

    if snapshot.top_expense_categories:
        top = snapshot.top_expense_categories[0]
        recs.append({
            "priority": 4,
            "action": "review_top_expense_category",
            "title": f"Review top spending category (ID {top['category_id']})",
            "impact": "medium",
            "detail": f"Spending {top['monthly_avg']}/month. A 10% reduction saves {top['monthly_avg']*0.1:.2f}/month.",
        })

    if snapshot.monthly_surplus < 0:
        recs.append({
            "priority": 0,
            "action": "reduce_expenses_urgently",
            "title": "Monthly expenses exceed income",
            "impact": "critical",
            "detail": "You are spending more than you earn. Immediate action required.",
        })

    recs.sort(key=lambda r: r["priority"])
    return recs
