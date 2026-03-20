from __future__ import annotations

import statistics
from datetime import date, timedelta
from typing import Optional
from dataclasses import dataclass, field

from sqlalchemy import func

from app.models import Transaction
from app import db


@dataclass
class MonthlyProjection:
    month: str          # YYYY-MM
    projected_income: float
    projected_expenses: float
    projected_net: float
    confidence: float   # 0.0 - 1.0


@dataclass
class IrregularExpense:
    category: str
    typical_month: str  # e.g. "December" (seasonality hint)
    estimated_amount: float
    frequency_months: int  # how often it occurs


@dataclass
class CashFlowForecastResult:
    current_balance_estimate: float
    monthly_projections: list[MonthlyProjection]
    irregular_expenses: list[IrregularExpense]
    avg_monthly_income: float
    avg_monthly_expenses: float
    overall_confidence: float
    trend: str          # "improving", "stable", "declining"
    message: str


def _get_monthly_totals(user_id: int, months_back: int):
    """Return dict of {YYYY-MM: {income: float, expenses: float}}."""
    cutoff = date.today() - timedelta(days=months_back * 30)
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
    totals: dict[str, dict] = {}
    for row in rows:
        m = row.month
        if m not in totals:
            totals[m] = {"income": 0.0, "expenses": 0.0}
        if row.type.lower() == "income":
            totals[m]["income"] += float(row.total or 0)
        else:
            totals[m]["expenses"] += float(row.total or 0)
    return totals


def _detect_irregular_expenses(user_id: int) -> list[IrregularExpense]:
    """Find categories that appear in fewer than half the months over 12-month history."""
    cutoff = date.today() - timedelta(days=365)
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.type == "expense",
        )
        .group_by("month", Transaction.category)
        .all()
    )

    cat_months: dict[str, list] = {}
    for row in rows:
        cat = row.category or "Uncategorized"
        if cat not in cat_months:
            cat_months[cat] = []
        cat_months[cat].append((row.month, float(row.total or 0)))

    total_months = 12
    irregular = []
    for cat, entries in cat_months.items():
        if len(entries) < total_months / 2:  # appears in fewer than 6 months
            amounts = [e[1] for e in entries]
            months_list = [e[0] for e in entries]
            # Find the month name with highest spend
            peak = max(entries, key=lambda x: x[1])
            peak_month_name = date(int(peak[0][:4]), int(peak[0][5:7]), 1).strftime("%B")
            avg_amount = statistics.mean(amounts)
            freq = max(1, round(total_months / len(entries)))
            irregular.append(
                IrregularExpense(
                    category=cat,
                    typical_month=peak_month_name,
                    estimated_amount=round(avg_amount, 2),
                    frequency_months=freq,
                )
            )
    return sorted(irregular, key=lambda x: -x.estimated_amount)[:5]


def get_cash_flow_forecast(
    user_id: int, forecast_months: int = 3
) -> CashFlowForecastResult:
    """
    Predict future cash flow for `forecast_months` ahead (1-6).
    Uses last 12 months of history for baseline.
    """
    forecast_months = max(1, min(6, forecast_months))

    totals = _get_monthly_totals(user_id, months_back=12)

    if not totals:
        return CashFlowForecastResult(
            current_balance_estimate=0.0,
            monthly_projections=[],
            irregular_expenses=[],
            avg_monthly_income=0.0,
            avg_monthly_expenses=0.0,
            overall_confidence=0.0,
            trend="stable",
            message="Not enough data to generate a forecast.",
        )

    sorted_months = sorted(totals.keys())

    incomes = [totals[m]["income"] for m in sorted_months]
    expenses = [totals[m]["expenses"] for m in sorted_months]

    avg_income = statistics.mean(incomes) if incomes else 0.0
    avg_expenses = statistics.mean(expenses) if expenses else 0.0

    # Trend: compare last 3 months vs previous 3 months net
    if len(sorted_months) >= 6:
        recent_net = statistics.mean(
            [totals[m]["income"] - totals[m]["expenses"] for m in sorted_months[-3:]]
        )
        older_net = statistics.mean(
            [totals[m]["income"] - totals[m]["expenses"] for m in sorted_months[-6:-3]]
        )
        if recent_net > older_net * 1.05:
            trend = "improving"
        elif recent_net < older_net * 0.95:
            trend = "declining"
        else:
            trend = "stable"
    else:
        trend = "stable"

    # Confidence based on data availability (more months = more confidence)
    n_months = len(sorted_months)
    base_confidence = min(1.0, n_months / 6.0)

    # Volatility penalty: high std_dev lowers confidence
    if len(expenses) >= 2:
        try:
            cv = statistics.stdev(expenses) / avg_expenses if avg_expenses > 0 else 0
            volatility_penalty = min(0.3, cv * 0.3)
        except statistics.StatisticsError:
            volatility_penalty = 0.0
    else:
        volatility_penalty = 0.15

    confidence = round(max(0.1, base_confidence - volatility_penalty), 2)

    # Project future months
    today = date.today()
    # Start from next month
    if today.month == 12:
        next_month = date(today.year + 1, 1, 1)
    else:
        next_month = date(today.year, today.month + 1, 1)

    projections = []
    for i in range(forecast_months):
        y = next_month.year
        m = next_month.month + i
        while m > 12:
            m -= 12
            y += 1
        month_str = f"{y:04d}-{m:02d}"

        # Confidence decays slightly for future months
        month_confidence = round(confidence * (0.95**i), 2)

        projections.append(
            MonthlyProjection(
                month=month_str,
                projected_income=round(avg_income, 2),
                projected_expenses=round(avg_expenses, 2),
                projected_net=round(avg_income - avg_expenses, 2),
                confidence=month_confidence,
            )
        )

    irregular = _detect_irregular_expenses(user_id)

    # Balance estimate = last month's net
    if sorted_months:
        last = sorted_months[-1]
        current_balance_estimate = round(totals[last]["income"] - totals[last]["expenses"], 2)
    else:
        current_balance_estimate = 0.0

    trend_messages = {
        "improving": "Your finances show a positive trend. Income is outpacing expenses recently.",
        "declining": "Caution: your net cash flow has been declining. Consider reviewing recurring expenses.",
        "stable": "Your cash flow is stable. Projections are based on recent averages.",
    }

    return CashFlowForecastResult(
        current_balance_estimate=current_balance_estimate,
        monthly_projections=projections,
        irregular_expenses=irregular,
        avg_monthly_income=round(avg_income, 2),
        avg_monthly_expenses=round(avg_expenses, 2),
        overall_confidence=confidence,
        trend=trend,
        message=trend_messages[trend],
    )