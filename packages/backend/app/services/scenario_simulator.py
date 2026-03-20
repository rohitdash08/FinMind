from __future__ import annotations

import statistics
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func

from app.models import Transaction
from app import db


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScenarioMonthResult:
    month: str               # YYYY-MM
    income: float
    expenses: float
    net: float
    cumulative_net: float


@dataclass
class ScenarioResult:
    scenario_name: str
    description: str
    monthly_results: list[ScenarioMonthResult]
    total_net_change: float   # vs baseline total net over N months
    break_even_month: Optional[str]  # month when cumulative goes positive
    recommendation: str


@dataclass
class ScenarioSimulationResult:
    baseline: ScenarioResult
    scenario: ScenarioResult
    net_impact_monthly: float   # scenario - baseline monthly net
    net_impact_total: float     # over full forecast period
    verdict: str                # "beneficial", "neutral", "detrimental"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALLOWED_SCENARIO_TYPES = {
    "reduce_category",    # reduce spending in a category by a %
    "increase_income",    # add to monthly income
    "increase_expense",   # add a new recurring expense
    "change_rent",        # change rent/mortgage by an amount
    "salary_change",      # change salary (income) by %
}


def _get_recent_averages(user_id: int, months_back: int = 3) -> tuple[float, float]:
    """Return (avg_income, avg_expenses) for the past N months."""
    cutoff = date.today() - timedelta(days=months_back * 31)
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            Transaction.type,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(Transaction.user_id == user_id, Transaction.date >= cutoff)
        .group_by("month", Transaction.type)
        .all()
    )

    by_month: dict[str, dict] = {}
    for row in rows:
        m = row.month
        if m not in by_month:
            by_month[m] = {"income": 0.0, "expenses": 0.0}
        if row.type.lower() == "income":
            by_month[m]["income"] += float(row.total or 0)
        else:
            by_month[m]["expenses"] += float(row.total or 0)

    if not by_month:
        return 0.0, 0.0

    avg_income = statistics.mean(v["income"] for v in by_month.values())
    avg_expenses = statistics.mean(v["expenses"] for v in by_month.values())
    return round(avg_income, 2), round(avg_expenses, 2)


def _get_category_avg(user_id: int, category: str, months_back: int = 3) -> float:
    """Return average monthly spend for a specific category."""
    cutoff = date.today() - timedelta(days=months_back * 31)
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.type == "expense",
            Transaction.category == category,
        )
        .group_by("month")
        .all()
    )
    if not rows:
        return 0.0
    totals = [float(r.total or 0) for r in rows]
    return round(statistics.mean(totals), 2)


def _build_monthly_results(
    base_income: float,
    base_expenses: float,
    months: int,
    start_month: Optional[date] = None,
) -> list[ScenarioMonthResult]:
    """Build N months of baseline results."""
    today = start_month or date.today()
    # Start from next month
    if today.month == 12:
        y, m = today.year + 1, 1
    else:
        y, m = today.year, today.month + 1

    results = []
    cumulative = 0.0
    for i in range(months):
        mo = m + i
        yr = y
        while mo > 12:
            mo -= 12
            yr += 1
        net = round(base_income - base_expenses, 2)
        cumulative = round(cumulative + net, 2)
        results.append(
            ScenarioMonthResult(
                month=f"{yr:04d}-{mo:02d}",
                income=base_income,
                expenses=base_expenses,
                net=net,
                cumulative_net=cumulative,
            )
        )
    return results


def run_scenario(
    user_id: int,
    scenario_type: str,
    value: float,
    category: Optional[str] = None,
    months: int = 6,
    scenario_name: Optional[str] = None,
) -> ScenarioSimulationResult:
    """
    Simulate a financial decision and compare to baseline.

    Args:
        user_id: JWT user id
        scenario_type: one of ALLOWED_SCENARIO_TYPES
        value: numeric magnitude of the change
          - reduce_category: percentage reduction (0-100)
          - increase_income: monthly amount to add
          - increase_expense: monthly amount to add
          - change_rent: new monthly rent amount (absolute)
          - salary_change: percentage change (-100 to +200)
        category: required for reduce_category
        months: forecast horizon (1-24)
        scenario_name: optional human-friendly name
    """
    months = max(1, min(24, months))

    if scenario_type not in ALLOWED_SCENARIO_TYPES:
        scenario_type = "increase_expense"

    avg_income, avg_expenses = _get_recent_averages(user_id)

    # Build baseline
    baseline_monthly = _build_monthly_results(avg_income, avg_expenses, months)
    baseline_total_net = sum(r.net for r in baseline_monthly)

    # Apply scenario
    scenario_income = avg_income
    scenario_expenses = avg_expenses
    desc = ""
    name = scenario_name or scenario_type.replace("_", " ").title()

    if scenario_type == "reduce_category":
        cat = category or "General"
        pct = max(0.0, min(100.0, value))
        cat_avg = _get_category_avg(user_id, cat)
        saving = round(cat_avg * pct / 100, 2)
        scenario_expenses = round(avg_expenses - saving, 2)
        desc = f"Reduce {cat} spending by {pct:.0f}% (-${saving:.2f}/month)."
        name = name or f"Cut {cat} by {pct:.0f}%"

    elif scenario_type == "increase_income":
        scenario_income = round(avg_income + value, 2)
        desc = f"Add ${value:.2f}/month of additional income."
        name = name or f"Income +${value:.2f}"

    elif scenario_type == "increase_expense":
        scenario_expenses = round(avg_expenses + value, 2)
        desc = f"Add ${value:.2f}/month of new expense."
        name = name or f"New expense +${value:.2f}"

    elif scenario_type == "change_rent":
        # value is the NEW rent amount
        old_rent = _get_category_avg(user_id, "Rent") or _get_category_avg(user_id, "rent")
        diff = round(value - old_rent, 2)
        scenario_expenses = round(avg_expenses + diff, 2)
        direction = "increase" if diff > 0 else "decrease"
        desc = f"Rent {direction} to ${value:.2f}/month (${abs(diff):.2f} change)."
        name = name or f"Rent → ${value:.2f}"

    elif scenario_type == "salary_change":
        pct = value  # e.g. 10 = 10% raise
        change = round(avg_income * pct / 100, 2)
        scenario_income = round(avg_income + change, 2)
        direction = "raise" if change > 0 else "cut"
        desc = f"Salary {direction} of {abs(pct):.1f}% (+${change:.2f}/month)."
        name = name or f"Salary {'+' if change>=0 else ''}{pct:.1f}%"

    scenario_monthly = _build_monthly_results(scenario_income, scenario_expenses, months)
    scenario_total_net = sum(r.net for r in scenario_monthly)

    net_impact_monthly = round(
        (scenario_income - scenario_expenses) - (avg_income - avg_expenses), 2
    )
    net_impact_total = round(scenario_total_net - baseline_total_net, 2)

    # Break-even month (when cumulative goes positive in scenario)
    break_even_month = None
    for r in scenario_monthly:
        if r.cumulative_net >= 0:
            break_even_month = r.month
            break

    # Verdict
    if net_impact_monthly > 10:
        verdict = "beneficial"
        recommendation = (
            f"This change improves your monthly cash flow by ${net_impact_monthly:.2f}. "
            f"Over {months} months, total gain: ${net_impact_total:.2f}."
        )
    elif net_impact_monthly < -10:
        verdict = "detrimental"
        recommendation = (
            f"This change reduces your monthly cash flow by ${abs(net_impact_monthly):.2f}. "
            f"Over {months} months, total cost: ${abs(net_impact_total):.2f}. Consider alternatives."
        )
    else:
        verdict = "neutral"
        recommendation = (
            f"This change has minimal financial impact (${net_impact_monthly:.2f}/month). "
            "Other factors may drive this decision."
        )

    def _make_scenario_result(monthly, total_net, s_name, s_desc):
        return ScenarioResult(
            scenario_name=s_name,
            description=s_desc,
            monthly_results=monthly,
            total_net_change=round(total_net - baseline_total_net, 2),
            break_even_month=break_even_month,
            recommendation=recommendation,
        )

    return ScenarioSimulationResult(
        baseline=ScenarioResult(
            scenario_name="Baseline",
            description="Current spending pattern with no changes.",
            monthly_results=baseline_monthly,
            total_net_change=0.0,
            break_even_month=None,
            recommendation="No change from current trajectory.",
        ),
        scenario=ScenarioResult(
            scenario_name=name,
            description=desc,
            monthly_results=scenario_monthly,
            total_net_change=round(scenario_total_net - baseline_total_net, 2),
            break_even_month=break_even_month,
            recommendation=recommendation,
        ),
        net_impact_monthly=net_impact_monthly,
        net_impact_total=net_impact_total,
        verdict=verdict,
    )