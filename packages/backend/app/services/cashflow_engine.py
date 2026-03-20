"""
Cash-flow Forecast Engine.

Forecasts 30/60/90 day cash flow using:
- Historical expense averages (recurring base spending)
- Scheduled recurring expenses (from recurring_expenses table)
- Upcoming bills from bills table
- Daily resolution for graph-ready output

Architecture:
1. Build daily projection timeline
2. Add recurring expenses at scheduled cadence
3. Add bills at their next_due_date
4. Apply income estimate (1.2x avg expenses)
5. Return daily + weekly + monthly aggregated views
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta
from collections import defaultdict
from enum import Enum

from ..models import Expense, RecurringExpense, Bill, RecurringCadence, BillCadence


class ForecastHorizon(int, Enum):
    THIRTY = 30
    SIXTY = 60
    NINETY = 90


@dataclass
class DailyProjection:
    date: str           # YYYY-MM-DD
    income: float       # Estimated income for this day
    expenses: float     # Scheduled outflows
    net: float          # income - expenses
    running_balance: float
    sources: list[str]  # What's driving the expenses


@dataclass
class CashFlowForecastResult:
    horizon_days: int
    start_date: str
    end_date: str
    starting_balance: float
    projected_end_balance: float
    total_projected_income: float
    total_projected_expenses: float
    net_cash_flow: float
    daily_projections: list[DailyProjection]
    weekly_summary: list[dict]
    monthly_summary: list[dict]
    key_dates: list[dict]   # Dates with large cashflow events
    generated_at: str


def _get_daily_avg_expense(user_id: int) -> float:
    """Calculate daily average expense from last 90 days of history."""
    cutoff = date.today() - timedelta(days=90)
    expenses = Expense.query.filter(
        Expense.user_id == user_id,
        Expense.spent_at >= cutoff,
    ).all()

    if not expenses:
        return 0.0

    total = sum(float(e.amount or 0) for e in expenses)
    days = max(1, (date.today() - cutoff).days)
    return total / days


def _get_recurring_schedule(
    user_id: int,
    start: date,
    end: date,
) -> dict[str, list[tuple[float, str]]]:
    """
    Build a dict of date -> [(amount, description)] for recurring expenses
    falling within [start, end].
    """
    schedule: dict[str, list[tuple[float, str]]] = defaultdict(list)
    recurrings = RecurringExpense.query.filter(
        RecurringExpense.user_id == user_id,
        RecurringExpense.active == True,
    ).all()

    for rec in recurrings:
        if not rec.start_date:
            continue
        amount = float(rec.amount or 0)
        desc = rec.notes or f"Recurring #{rec.id}"
        cadence = rec.cadence

        current = max(rec.start_date, start)
        while current <= end:
            if rec.end_date and current > rec.end_date:
                break
            date_str = current.isoformat()
            schedule[date_str].append((amount, desc))

            # Advance by cadence
            if cadence == RecurringCadence.DAILY:
                current += timedelta(days=1)
            elif cadence == RecurringCadence.WEEKLY:
                current += timedelta(weeks=1)
            elif cadence == RecurringCadence.MONTHLY:
                # Advance by ~30 days, keeping day-of-month
                month = current.month + 1
                year = current.year + (1 if month > 12 else 0)
                month = month if month <= 12 else 1
                import calendar
                max_day = calendar.monthrange(year, month)[1]
                current = current.replace(year=year, month=month, day=min(current.day, max_day))
            elif cadence == RecurringCadence.YEARLY:
                current = current.replace(year=current.year + 1)
            else:
                break  # Unknown cadence

    return dict(schedule)


def _get_bill_schedule(
    user_id: int,
    start: date,
    end: date,
) -> dict[str, list[tuple[float, str]]]:
    """Build dict of date -> [(amount, bill_name)] for upcoming bills."""
    schedule: dict[str, list[tuple[float, str]]] = defaultdict(list)
    bills = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.active == True,
        Bill.next_due_date >= start,
        Bill.next_due_date <= end,
    ).all()

    for bill in bills:
        date_str = bill.next_due_date.isoformat()
        amount = float(bill.amount or 0)
        schedule[date_str].append((amount, bill.name or f"Bill #{bill.id}"))

    return dict(schedule)


def _aggregate_weekly(daily: list[DailyProjection]) -> list[dict]:
    """Group daily projections into weekly summaries."""
    if not daily:
        return []
    weeks: dict[str, dict] = {}
    for proj in daily:
        d = datetime.strptime(proj.date, "%Y-%m-%d").date()
        # Week key: year+week number
        week_key = d.strftime("%Y-W%W")
        if week_key not in weeks:
            weeks[week_key] = {"week": week_key, "income": 0.0, "expenses": 0.0, "net": 0.0, "days": 0}
        weeks[week_key]["income"] += proj.income
        weeks[week_key]["expenses"] += proj.expenses
        weeks[week_key]["net"] += proj.net
        weeks[week_key]["days"] += 1

    return list(weeks.values())


def _aggregate_monthly(daily: list[DailyProjection]) -> list[dict]:
    """Group daily projections into monthly summaries."""
    months: dict[str, dict] = {}
    for proj in daily:
        month_key = proj.date[:7]  # YYYY-MM
        if month_key not in months:
            months[month_key] = {"month": month_key, "income": 0.0, "expenses": 0.0, "net": 0.0}
        months[month_key]["income"] += proj.income
        months[month_key]["expenses"] += proj.expenses
        months[month_key]["net"] += proj.net

    return list(months.values())


def _find_key_dates(daily: list[DailyProjection], threshold: float) -> list[dict]:
    """Find dates with unusually large cash flow events."""
    avg_expense = sum(d.expenses for d in daily) / len(daily) if daily else 0
    key = []
    for proj in daily:
        if proj.expenses > avg_expense * 2 and proj.expenses > threshold:
            key.append({
                "date": proj.date,
                "expenses": round(proj.expenses, 2),
                "sources": proj.sources,
                "type": "large_outflow",
            })
        if proj.running_balance < 0:
            key.append({
                "date": proj.date,
                "running_balance": round(proj.running_balance, 2),
                "type": "negative_balance_warning",
            })
    return key[:10]  # Max 10 key dates


def get_cashflow_forecast(
    user_id: int,
    horizon: int = 30,
    starting_balance: float = 0.0,
) -> CashFlowForecastResult:
    """
    Generate 30/60/90 day cash flow forecast.

    Args:
        user_id: User ID
        horizon: Forecast days (30, 60, or 90)
        starting_balance: Current balance to project forward

    Returns:
        CashFlowForecastResult with daily/weekly/monthly views.
    """
    horizon = min(90, max(1, horizon))
    start = date.today()
    end = start + timedelta(days=horizon - 1)

    # Base daily expense from history
    daily_base_expense = _get_daily_avg_expense(user_id)

    # Estimate daily income (20% above average expense)
    daily_income = daily_base_expense * 1.20 if daily_base_expense > 0 else 50.0

    # Get scheduled items
    recurring_schedule = _get_recurring_schedule(user_id, start, end)
    bill_schedule = _get_bill_schedule(user_id, start, end)

    # Build daily projections
    daily_projections: list[DailyProjection] = []
    running_balance = starting_balance
    total_income = 0.0
    total_expenses = 0.0

    current = start
    while current <= end:
        date_str = current.isoformat()

        # Base expenses
        day_expense = daily_base_expense
        sources = []

        # Add recurring expenses
        for amount, desc in recurring_schedule.get(date_str, []):
            day_expense += amount
            sources.append(f"{desc} ({amount:.2f})")

        # Add bills
        for amount, name in bill_schedule.get(date_str, []):
            day_expense += amount
            sources.append(f"Bill: {name} ({amount:.2f})")

        net = daily_income - day_expense
        running_balance += net
        total_income += daily_income
        total_expenses += day_expense

        daily_projections.append(DailyProjection(
            date=date_str,
            income=round(daily_income, 2),
            expenses=round(day_expense, 2),
            net=round(net, 2),
            running_balance=round(running_balance, 2),
            sources=sources,
        ))

        current += timedelta(days=1)

    weekly = _aggregate_weekly(daily_projections)
    monthly = _aggregate_monthly(daily_projections)
    key_dates = _find_key_dates(daily_projections, daily_base_expense * 3)

    return CashFlowForecastResult(
        horizon_days=horizon,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        starting_balance=starting_balance,
        projected_end_balance=round(running_balance, 2),
        total_projected_income=round(total_income, 2),
        total_projected_expenses=round(total_expenses, 2),
        net_cash_flow=round(total_income - total_expenses, 2),
        daily_projections=daily_projections,
        weekly_summary=weekly,
        monthly_summary=monthly,
        key_dates=key_dates,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )