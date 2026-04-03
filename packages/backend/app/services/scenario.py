from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from app.models import db, Expense, Income, RecurringBill, Budget


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _avg_monthly(uid: int, months: int, model, date_field: str, amount_field: str) -> float:
    """Return average monthly total for the given ORM model over last N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    rows = (
        db.session.query(model)
        .filter(getattr(model, "user_id") == uid, getattr(model, date_field) >= cutoff)
        .all()
    )
    if not rows:
        return 0.0
    total = sum(float(getattr(r, amount_field) or 0) for r in rows)
    return total / months


def _category_spending(uid: int, months: int = 3) -> dict[int, float]:
    """Average monthly spending per category over the last N months."""
    cutoff = date.today() - timedelta(days=30 * months)
    expenses = (
        db.session.query(Expense)
        .filter(Expense.user_id == uid, Expense.date >= cutoff)
        .all()
    )
    totals: dict[int, float] = {}
    for e in expenses:
        cat = e.category_id or 0
        totals[cat] = totals.get(cat, 0.0) + float(e.amount or 0)
    return {cat: total / months for cat, total in totals.items()}


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

class ScenarioResult:
    """Holds the result of a single scenario simulation."""

    def __init__(
        self,
        scenario_id: str,
        label: str,
        months: int,
        baseline_net: float,
        projected_net: float,
        monthly_breakdowns: list[dict],
        impact_summary: dict,
    ) -> None:
        self.scenario_id = scenario_id
        self.label = label
        self.months = months
        self.baseline_net = baseline_net
        self.projected_net = projected_net
        self.monthly_breakdowns = monthly_breakdowns
        self.impact_summary = impact_summary

    def to_dict(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "label": self.label,
            "months": self.months,
            "baseline_monthly_net": round(self.baseline_net, 2),
            "projected_monthly_net": round(self.projected_net, 2),
            "net_change": round(self.projected_net - self.baseline_net, 2),
            "net_change_pct": (
                round((self.projected_net - self.baseline_net) / abs(self.baseline_net) * 100, 1)
                if self.baseline_net != 0
                else 0.0
            ),
            "monthly_breakdowns": self.monthly_breakdowns,
            "impact_summary": self.impact_summary,
        }


# ---------------------------------------------------------------------------
# Core simulation engine
# ---------------------------------------------------------------------------

def _baseline(uid: int, months: int = 3) -> tuple[float, float]:
    """Return (avg_monthly_income, avg_monthly_expense)."""
    income = _avg_monthly(uid, months, Income, "date", "amount")
    expense = _avg_monthly(uid, months, Expense, "date", "amount")
    return income, expense


def simulate_scenario(uid: int, scenario: dict[str, Any], horizon_months: int = 12) -> ScenarioResult:
    """
    Simulate a what-if financial scenario.

    Supported scenario types (via scenario["type"]):
      - expense_reduction : reduce spending in a category by a %
      - expense_increase  : increase spending in a category by a %
      - income_change     : change monthly income by an absolute or % amount
      - rent_change       : alias for a fixed recurring bill change
      - savings_goal      : determine months to reach a savings target given current net
      - debt_payoff       : model debt payoff with monthly payment

    Required keys per type:
      expense_reduction/increase:
        category_id (int), change_pct (float, positive)
      income_change:
        change_amount (float) OR change_pct (float)
      rent_change:
        old_rent (float), new_rent (float)
      savings_goal:
        target_amount (float)
      debt_payoff:
        principal (float), apr (float), monthly_payment (float)
    """
    stype = scenario.get("type", "expense_reduction")
    base_income, base_expense = _baseline(uid)
    base_net = base_income - base_expense

    proj_income = base_income
    proj_expense = base_expense

    label = "Custom Scenario"
    impact: dict[str, Any] = {}

    # --- expense_reduction / expense_increase ---
    if stype in ("expense_reduction", "expense_increase"):
        cat_id = int(scenario.get("category_id", 0))
        change_pct = float(scenario.get("change_pct", 10.0))
        if stype == "expense_increase":
            change_pct = -abs(change_pct)  # increases cost = negative for net
        else:
            change_pct = abs(change_pct)  # reduction = positive for net

        cat_spending = _category_spending(uid)
        cat_avg = cat_spending.get(cat_id, 0.0)
        savings_per_month = cat_avg * (change_pct / 100.0)
        proj_expense = base_expense - savings_per_month
        label = (
            f"Reduce category {cat_id} spending by {abs(change_pct):.0f}%"
            if stype == "expense_reduction"
            else f"Increase category {cat_id} spending by {abs(change_pct):.0f}%"
        )
        impact = {
            "category_id": cat_id,
            "category_avg_monthly": round(cat_avg, 2),
            "monthly_saving": round(savings_per_month, 2),
            "annual_saving": round(savings_per_month * 12, 2),
        }

    # --- income_change ---
    elif stype == "income_change":
        if "change_amount" in scenario:
            delta = float(scenario["change_amount"])
        else:
            delta = base_income * float(scenario.get("change_pct", 10.0)) / 100.0
        proj_income = base_income + delta
        label = f"Income change by {delta:+.2f}/month"
        impact = {
            "income_delta_monthly": round(delta, 2),
            "income_delta_annual": round(delta * 12, 2),
            "new_monthly_income": round(proj_income, 2),
        }

    # --- rent_change ---
    elif stype == "rent_change":
        old_rent = float(scenario.get("old_rent", 0.0))
        new_rent = float(scenario.get("new_rent", 0.0))
        delta = new_rent - old_rent
        proj_expense = base_expense + delta
        label = f"Rent change {old_rent:.0f} -> {new_rent:.0f}/month"
        impact = {
            "rent_increase": round(delta, 2),
            "annual_impact": round(delta * 12, 2),
        }

    # --- savings_goal ---
    elif stype == "savings_goal":
        target = float(scenario.get("target_amount", 10000.0))
        net = base_net
        if net <= 0:
            months_needed = None
            label = "Savings Goal (unachievable — negative net)"
        else:
            months_needed = math.ceil(target / net)
            label = f"Months to save {target:.0f} at current rate"
        impact = {
            "target_amount": target,
            "current_monthly_net": round(net, 2),
            "months_to_goal": months_needed,
            "achievable": months_needed is not None,
        }
        horizon_months = min(horizon_months, months_needed or horizon_months)

    # --- debt_payoff ---
    elif stype == "debt_payoff":
        principal = float(scenario.get("principal", 10000.0))
        apr = float(scenario.get("apr", 15.0)) / 100.0 / 12.0
        payment = float(scenario.get("monthly_payment", 300.0))
        balance = principal
        months_to_payoff = 0
        total_interest = 0.0
        while balance > 0 and months_to_payoff < 600:
            interest = balance * apr
            total_interest += interest
            balance = balance + interest - payment
            if balance < 0:
                balance = 0
            months_to_payoff += 1
        label = f"Debt payoff: {principal:.0f} at {apr*1200:.1f}% APR"
        proj_expense = base_expense + payment
        impact = {
            "months_to_payoff": months_to_payoff,
            "total_interest_paid": round(total_interest, 2),
            "monthly_payment": payment,
            "total_cost": round(principal + total_interest, 2),
        }

    proj_net = proj_income - proj_expense

    # Build monthly breakdown
    cumulative_savings = 0.0
    monthly_breakdowns = []
    for i in range(1, horizon_months + 1):
        month_net = proj_net
        cumulative_savings += month_net
        monthly_breakdowns.append({
            "month": i,
            "projected_income": round(proj_income, 2),
            "projected_expense": round(proj_expense, 2),
            "net": round(month_net, 2),
            "cumulative_net": round(cumulative_savings, 2),
        })

    return ScenarioResult(
        scenario_id=stype,
        label=label,
        months=horizon_months,
        baseline_net=base_net,
        projected_net=proj_net,
        monthly_breakdowns=monthly_breakdowns,
        impact_summary=impact,
    )


def compare_scenarios(uid: int, scenarios: list[dict], horizon_months: int = 12) -> list[dict]:
    """Run multiple scenarios and return them sorted by projected_monthly_net descending."""
    results = [simulate_scenario(uid, s, horizon_months).to_dict() for s in scenarios]
    results.sort(key=lambda r: r["projected_monthly_net"], reverse=True)
    return results
