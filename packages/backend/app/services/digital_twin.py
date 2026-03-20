"""
Personal Financial Digital Twin Simulator.

Simulates long-term financial trajectory based on historical spending patterns.
Includes:
- Multi-year monthly projections with inflation adjustment
- Life event simulation: salary raise, job loss, new expense category, debt payoff
- Risk detection: emergency fund depletion, negative savings, high burn rate
- Savings outlook: months to reach target savings goal
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta
from collections import defaultdict
import math

from ..models import Expense, Bill


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

DEFAULT_INFLATION_RATE = 0.03      # 3% annual inflation
DEFAULT_INCOME_GROWTH = 0.02       # 2% annual income growth
EMERGENCY_FUND_MONTHS = 3          # Threshold for emergency fund warning


# ──────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────

@dataclass
class LifeEvent:
    """A simulated life change affecting the financial model."""
    event_type: str        # "salary_raise", "job_loss", "new_expense", "debt_payoff", "windfall"
    month_offset: int      # months from simulation start (0-based)
    value: float           # amount / percentage depending on event_type
    label: str = ""


@dataclass
class MonthProjection:
    month: str             # YYYY-MM
    income: float          # estimated income
    expenses: float        # estimated expenses
    net: float             # income - expenses
    savings_balance: float # cumulative savings
    risk_flags: list[str] = field(default_factory=list)


@dataclass
class RiskAssessment:
    risk_level: str        # "low", "medium", "high", "critical"
    risks: list[str]
    opportunities: list[str]


@dataclass
class SavingsOutlook:
    target_amount: float
    months_to_reach: Optional[int]   # None if goal unreachable
    estimated_date: Optional[str]


@dataclass
class DigitalTwinResult:
    projection_months: int
    monthly_projections: list[MonthProjection]
    risk_assessment: RiskAssessment
    savings_outlook: Optional[SavingsOutlook]
    baseline_monthly_income: float
    baseline_monthly_expenses: float
    inflation_rate: float
    life_events_applied: list[str]
    generated_at: str


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _get_monthly_averages(expenses: list, bills: list) -> tuple[float, float]:
    """
    Estimate baseline monthly income and expenses from historical data.
    Income proxy = max monthly spending (assumes user spends most of what they earn).
    Expenses = average monthly total across history.
    """
    monthly_totals: dict[str, float] = defaultdict(float)
    for exp in expenses:
        if exp.date:
            key = exp.date.strftime("%Y-%m")
            monthly_totals[key] += float(exp.amount or 0)

    if not monthly_totals:
        return 3000.0, 2500.0  # Reasonable defaults if no data

    values = list(monthly_totals.values())
    avg_expenses = sum(values) / len(values)
    # Income proxy: 20% more than average expenses (assume some savings)
    estimated_income = avg_expenses * 1.20

    # Add recurring bills
    total_bill_amount = sum(float(b.amount or 0) for b in bills if getattr(b, "status", "") != "paid")

    return round(estimated_income, 2), round(avg_expenses + total_bill_amount / 12, 2)


def _apply_life_events(
    month_idx: int,
    income: float,
    expenses: float,
    life_events: list[LifeEvent],
) -> tuple[float, float]:
    """Apply life events that activate at or before month_idx."""
    for event in life_events:
        if event.month_offset != month_idx:
            continue
        if event.event_type == "salary_raise":
            income *= (1 + event.value / 100)
        elif event.event_type == "job_loss":
            income *= (1 - event.value / 100)  # value = income reduction %
        elif event.event_type == "new_expense":
            expenses += event.value  # monthly addition
        elif event.event_type == "debt_payoff":
            expenses -= event.value  # monthly reduction
        elif event.event_type == "windfall":
            income += event.value   # one-time addition
    return income, expenses


def _risk_assessment(
    projections: list[MonthProjection],
    baseline_income: float,
    baseline_expenses: float,
) -> RiskAssessment:
    """Assess risks from the projection timeline."""
    risks = []
    opportunities = []

    # Check for negative savings balance
    negative_months = [p.month for p in projections if p.savings_balance < 0]
    if negative_months:
        risks.append(f"Projected negative savings balance in {len(negative_months)} month(s), starting {negative_months[0]}.")

    # Check burn rate
    if baseline_expenses > baseline_income * 0.90:
        risks.append("Burn rate >90% of income leaves minimal safety margin.")

    # Emergency fund check (< 3 months of expenses)
    emergency_threshold = baseline_expenses * EMERGENCY_FUND_MONTHS
    end_balance = projections[-1].savings_balance if projections else 0
    if end_balance < emergency_threshold:
        risks.append(f"Projected end balance (${end_balance:.0f}) below 3-month emergency fund (${emergency_threshold:.0f}).")

    # Consecutive negative net months
    consecutive_negative = 0
    max_consecutive = 0
    for p in projections:
        if p.net < 0:
            consecutive_negative += 1
            max_consecutive = max(max_consecutive, consecutive_negative)
        else:
            consecutive_negative = 0
    if max_consecutive >= 3:
        risks.append(f"Projected {max_consecutive} consecutive months of negative net cash flow.")

    # Opportunities
    positive_months = [p for p in projections if p.net > 0]
    if len(positive_months) > len(projections) * 0.8:
        opportunities.append("80%+ months projected positive — strong base for building savings.")

    avg_net = sum(p.net for p in projections) / len(projections) if projections else 0
    if avg_net > 200:
        opportunities.append(f"Average monthly surplus of ${avg_net:.0f} — consider automated investment.")

    # Risk level
    if len(negative_months) > len(projections) * 0.4 or end_balance < 0:
        risk_level = "critical"
    elif len(risks) >= 3:
        risk_level = "high"
    elif len(risks) >= 1:
        risk_level = "medium"
    else:
        risk_level = "low"

    return RiskAssessment(
        risk_level=risk_level,
        risks=risks,
        opportunities=opportunities,
    )


def _savings_outlook(
    projections: list[MonthProjection],
    target: float,
    today_str: str,
) -> SavingsOutlook:
    """Estimate when the savings target will be reached."""
    for proj in projections:
        if proj.savings_balance >= target:
            return SavingsOutlook(
                target_amount=target,
                months_to_reach=projections.index(proj) + 1,
                estimated_date=proj.month,
            )
    return SavingsOutlook(
        target_amount=target,
        months_to_reach=None,
        estimated_date=None,
    )


def run_digital_twin(
    user_id: int,
    projection_months: int = 24,
    life_events: Optional[list[dict]] = None,
    savings_target: Optional[float] = None,
    inflation_rate: float = DEFAULT_INFLATION_RATE,
    starting_balance: float = 0.0,
) -> DigitalTwinResult:
    """
    Run a financial digital twin simulation.

    Args:
        user_id: User ID
        projection_months: How many months to project (1-120)
        life_events: List of life event dicts with keys: event_type, month_offset, value, label
        savings_target: Optional savings goal amount for outlook calculation
        inflation_rate: Annual inflation rate (default 3%)
        starting_balance: Current savings/starting balance

    Returns:
        DigitalTwinResult with monthly projections, risks, and savings outlook.
    """
    projection_months = max(1, min(120, projection_months))
    inflation_rate = max(0.0, min(0.5, inflation_rate))

    # Load historical data
    cutoff = date.today() - timedelta(days=365)
    expenses = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.date >= cutoff,
    ).all()

    bills = Bill.query.filter(Bill.user_id == user_id).all()

    baseline_income, baseline_expenses = _get_monthly_averages(expenses, bills)

    # Parse life events
    parsed_events: list[LifeEvent] = []
    event_labels: list[str] = []
    if life_events:
        for ev in life_events:
            try:
                parsed_events.append(LifeEvent(
                    event_type=ev.get("event_type", ""),
                    month_offset=int(ev.get("month_offset", 0)),
                    value=float(ev.get("value", 0)),
                    label=ev.get("label", ev.get("event_type", "")),
                ))
                event_labels.append(ev.get("label", ev.get("event_type", "")))
            except (ValueError, KeyError):
                continue

    # Run month-by-month projection
    monthly_projections: list[MonthProjection] = []
    savings_balance = starting_balance
    current_income = baseline_income
    current_expenses = baseline_expenses

    today = date.today()

    for month_idx in range(projection_months):
        # Monthly inflation adjustment (applied annually in monthly steps)
        monthly_inflation = (1 + inflation_rate) ** (1 / 12)
        current_expenses *= monthly_inflation

        # Apply life events for this month
        current_income, current_expenses = _apply_life_events(
            month_idx, current_income, current_expenses, parsed_events
        )

        net = current_income - current_expenses
        savings_balance += net

        # Calculate month label
        target_month = today + timedelta(days=30 * (month_idx + 1))
        month_str = target_month.strftime("%Y-%m")

        risk_flags = []
        if net < 0:
            risk_flags.append("negative_net")
        if savings_balance < 0:
            risk_flags.append("negative_balance")
        if current_expenses > current_income * 0.95:
            risk_flags.append("high_burn_rate")

        monthly_projections.append(MonthProjection(
            month=month_str,
            income=round(current_income, 2),
            expenses=round(current_expenses, 2),
            net=round(net, 2),
            savings_balance=round(savings_balance, 2),
            risk_flags=risk_flags,
        ))

    risk = _risk_assessment(monthly_projections, baseline_income, baseline_expenses)

    savings_out = None
    if savings_target is not None and savings_target > 0:
        savings_out = _savings_outlook(monthly_projections, savings_target, today.isoformat())

    return DigitalTwinResult(
        projection_months=projection_months,
        monthly_projections=monthly_projections,
        risk_assessment=risk,
        savings_outlook=savings_out,
        baseline_monthly_income=baseline_income,
        baseline_monthly_expenses=baseline_expenses,
        inflation_rate=inflation_rate,
        life_events_applied=event_labels,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )