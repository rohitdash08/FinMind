"""Cash-flow Forecast Engine.

Predicts future cash flow based on historical patterns:
- Time-series analysis of income/expenses
- Seasonal pattern detection (weekly, monthly, yearly)
- Trend projection with configurable horizons
- Best/worst/expected case scenarios
- Recurring transaction prediction
- Cash reserve warnings (low balance alerts)
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.cashflow")


class CashFlowForecast:
    """Result of a cash-flow forecast."""

    def __init__(self, forecast_id: str, horizon_days: int):
        self.forecast_id = forecast_id
        self.horizon_days = horizon_days
        self.daily_forecasts = []
        self.summary = {}
        self.warnings = []

    def to_dict(self) -> dict:
        return {
            "forecast_id": self.forecast_id,
            "horizon_days": self.horizon_days,
            "daily_forecasts": self.daily_forecasts,
            "summary": self.summary,
            "warnings": self.warnings,
        }


class CashFlowForecastService:
    """Forecast future cash flow from historical transactions."""

    def __init__(self):
        pass

    def _daily_totals(self, transactions: list[dict]) -> dict:
        """Aggregate transactions into daily totals."""
        daily = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
        for tx in transactions:
            date = str(tx.get("date", ""))[:10]
            amount = abs(float(tx.get("amount", 0)))
            tx_type = tx.get("type", "").lower()
            if tx_type == "income" or (tx.get("amount", 0) > 0):
                daily[date]["income"] += amount
            else:
                daily[date]["expense"] += amount
        return dict(daily)

    def _weekly_pattern(self, daily_totals: dict) -> dict:
        """Detect day-of-week spending patterns."""
        dow = defaultdict(list)
        for date, totals in daily_totals.items():
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                dow[dt.weekday()].append(totals["expense"])
            except ValueError:
                continue

        pattern = {}
        for day, amounts in dow.items():
            avg = sum(amounts) / len(amounts) if amounts else 0
            pattern[day] = round(avg, 2)
        return pattern

    def _monthly_pattern(self, daily_totals: dict) -> dict:
        """Detect day-of-month patterns (e.g., rent on 1st)."""
        dom = defaultdict(list)
        for date, totals in daily_totals.items():
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                dom[dt.day].append(totals["expense"])
            except ValueError:
                continue

        pattern = {}
        for day, amounts in dom.items():
            avg = sum(amounts) / len(amounts) if amounts else 0
            pattern[day] = round(avg, 2)
        return pattern

    def _detect_recurring(self, transactions: list[dict],
                           min_occurrences: int = 3) -> list[dict]:
        """Detect recurring transactions (same amount, similar timing)."""
        by_amount = defaultdict(list)
        for tx in transactions:
            amt = round(abs(float(tx.get("amount", 0))), 2)
            if amt > 0:
                by_amount[amt].append(tx)

        recurring = []
        for amount, txs in by_amount.items():
            if len(txs) >= min_occurrences:
                # Check if timing is regular
                dates = sorted([str(t.get("date", ""))[:10] for t in txs])
                intervals = []
                for i in range(1, len(dates)):
                    try:
                        d1 = datetime.strptime(dates[i-1], "%Y-%m-%d")
                        d2 = datetime.strptime(dates[i], "%Y-%m-%d")
                        intervals.append((d2 - d1).days)
                    except ValueError:
                        continue

                if intervals:
                    avg_interval = sum(intervals) / len(intervals)
                    recurring.append({
                        "amount": amount,
                        "frequency_days": round(avg_interval, 1),
                        "occurrences": len(txs),
                        "type": "monthly" if 25 <= avg_interval <= 35 else
                               "weekly" if 5 <= avg_interval <= 9 else
                               "irregular",
                        "last_date": dates[-1],
                    })

        return recurring

    def _calculate_trend(self, daily_totals: dict, days_back: int = 30) -> dict:
        """Calculate income/expense trends."""
        sorted_dates = sorted(daily_totals.keys())[-days_back:]

        if len(sorted_dates) < 3:
            return {"income_trend": 0, "expense_trend": 0, "direction": "stable"}

        # Simple linear regression
        incomes = [daily_totals[d]["income"] for d in sorted_dates]
        expenses = [daily_totals[d]["expense"] for d in sorted_dates]
        n = len(sorted_dates)
        x = list(range(n))

        def slope(y_vals):
            if n < 2:
                return 0
            mean_x = sum(x) / n
            mean_y = sum(y_vals) / n
            ss_xy = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y_vals))
            ss_xx = sum((xi - mean_x) ** 2 for xi in x)
            return ss_xy / ss_xx if ss_xx != 0 else 0

        inc_slope = slope(incomes)
        exp_slope = slope(expenses)

        return {
            "income_trend": round(inc_slope, 2),
            "expense_trend": round(exp_slope, 2),
            "direction": "improving" if inc_slope > exp_slope else
                        "declining" if exp_slope > inc_slope else "stable",
        }

    def forecast(self, transactions: list[dict],
                 horizon_days: int = 30,
                 current_balance: float = 0) -> dict:
        """Generate cash-flow forecast."""
        forecast_id = str(uuid4())[:8]

        # Aggregate historical data
        daily_totals = self._daily_totals(transactions)

        # Detect patterns
        weekly_pattern = self._weekly_pattern(daily_totals)
        monthly_pattern = self._monthly_pattern(daily_totals)
        recurring = self._detect_recurring(transactions)
        trend = self._calculate_trend(daily_totals)

        # Generate daily forecasts
        today = datetime.now(timezone.utc).date()
        daily_forecasts = []
        balance = current_balance
        total_income = 0
        total_expense = 0

        # Calculate averages
        all_incomes = [v["income"] for v in daily_totals.values()]
        all_expenses = [v["expense"] for v in daily_totals.values()]
        avg_daily_income = sum(all_incomes) / max(len(all_incomes), 1)
        avg_daily_expense = sum(all_expenses) / max(len(all_expenses), 1)

        for day_offset in range(1, horizon_days + 1):
            future_date = today + timedelta(days=day_offset)
            weekday = future_date.weekday()
            monthday = future_date.day

            # Base prediction from patterns
            predicted_expense = monthly_pattern.get(monthday,
                                    weekly_pattern.get(weekday, avg_daily_expense))

            # Apply trend adjustment
            trend_factor = 1 + (trend["expense_trend"] * day_offset / 100)
            predicted_expense *= max(0.5, min(2.0, trend_factor))

            predicted_income = avg_daily_income
            income_trend_factor = 1 + (trend["income_trend"] * day_offset / 100)
            predicted_income *= max(0.5, min(2.0, income_trend_factor))

            # Add expected recurring transactions
            for rec in recurring:
                freq = rec["frequency_days"]
                if freq > 0 and day_offset % int(freq) == 0:
                    predicted_expense += rec["amount"]

            net = predicted_income - predicted_expense
            balance += net
            total_income += predicted_income
            total_expense += predicted_expense

            daily_forecasts.append({
                "date": future_date.isoformat(),
                "predicted_income": round(predicted_income, 2),
                "predicted_expense": round(predicted_expense, 2),
                "net": round(net, 2),
                "projected_balance": round(balance, 2),
            })

        # Warnings
        warnings = []
        if balance < 0:
            # Find first negative balance date
            for df in daily_forecasts:
                if df["projected_balance"] < 0:
                    warnings.append({
                        "type": "negative_balance",
                        "severity": "critical",
                        "message": f"Projected negative balance on {df['date']}",
                        "projected_balance": df["projected_balance"],
                    })
                    break

        if balance < current_balance * 0.2:
            warnings.append({
                "type": "low_reserve",
                "severity": "warning",
                "message": f"Balance projected to drop to {balance:.2f} ({horizon_days} days)",
            })

        result = {
            "forecast_id": forecast_id,
            "horizon_days": horizon_days,
            "current_balance": round(current_balance, 2),
            "projected_end_balance": round(balance, 2),
            "total_predicted_income": round(total_income, 2),
            "total_predicted_expense": round(total_expense, 2),
            "net_change": round(total_income - total_expense, 2),
            "trend": trend,
            "recurring_transactions": recurring,
            "daily_forecasts": daily_forecasts,
            "warnings": warnings,
        }

        return result
