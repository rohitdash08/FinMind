from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime, timedelta, date
import statistics

_transactions: Dict[str, List[Dict]] = defaultdict(list)
_income_entries: Dict[str, List[Dict]] = defaultdict(list)

class CashFlowForecastEngine:
    """
    Forecasts future cash flow using historical spending and income patterns.
    Uses exponential smoothing and seasonal decomposition.
    """

    ALPHA = 0.3  # Exponential smoothing weight

    def forecast(self, user_id: str, months_ahead: int = 3,
                 current_balance: float = 0) -> Dict[str, Any]:
        """Generate cash flow forecast for the next N months."""
        history = self._get_monthly_history(user_id, lookback_months=6)
        if not history:
            return {"forecast": [], "summary": {"error": "insufficient history"}}

        # Extract spending and income series
        months_sorted = sorted(history.keys())
        spending_series = [history[m]["spending"] for m in months_sorted]
        income_series = [history[m]["income"] for m in months_sorted]

        # Smooth the series
        smoothed_spend = self._exponential_smooth(spending_series)
        smoothed_income = self._exponential_smooth(income_series)

        # Project forward
        last_spend = smoothed_spend[-1] if smoothed_spend else 0
        last_income = smoothed_income[-1] if smoothed_income else 0

        # Calculate trend
        spend_trend = self._calc_trend(spending_series)
        income_trend = self._calc_trend(income_series)

        forecast = []
        balance = current_balance
        now = datetime.utcnow()
        month = now.month
        year = now.year

        for i in range(months_ahead):
            month += 1
            if month > 12:
                month = 1
                year += 1

            proj_spend = max(0, last_spend + spend_trend * (i + 1))
            proj_income = max(0, last_income + income_trend * (i + 1))
            net = proj_income - proj_spend
            balance += net

            # Confidence decreases with forecast distance
            confidence = max(0.5, 0.95 - i * 0.15)

            forecast.append({
                "month": month,
                "year": year,
                "month_label": f"{year}-{month:02d}",
                "projected_income": round(proj_income, 2),
                "projected_spending": round(proj_spend, 2),
                "projected_net": round(net, 2),
                "projected_balance": round(balance, 2),
                "confidence": round(confidence, 2),
                "scenario": {
                    "optimistic": round(balance + abs(net) * 0.2, 2),
                    "pessimistic": round(balance - abs(net) * 0.2, 2),
                },
            })

        summary = self._generate_summary(forecast, history)
        return {
            "forecast": forecast,
            "historical_summary": {
                "avg_monthly_spending": round(statistics.mean(spending_series), 2) if spending_series else 0,
                "avg_monthly_income": round(statistics.mean(income_series), 2) if income_series else 0,
                "months_analyzed": len(months_sorted),
            },
            "summary": summary,
        }

    def add_income(self, user_id: str, amount: float, date_str: str,
                   source: str = "salary") -> Dict:
        entry = {
            "amount": amount,
            "date": date_str,
            "source": source,
        }
        _income_entries[user_id].append(entry)
        return entry

    def _get_monthly_history(self, user_id: str, lookback_months: int = 6) -> Dict[str, Dict]:
        cutoff = datetime.utcnow() - timedelta(days=lookback_months * 30)
        result: Dict[str, Dict] = {}

        for t in _transactions.get(user_id, []):
            try:
                d = datetime.fromisoformat(t["date"])
                if d < cutoff:
                    continue
                key = f"{d.year}-{d.month:02d}"
                if key not in result:
                    result[key] = {"spending": 0, "income": 0}
                result[key]["spending"] += abs(float(t.get("amount", 0)))
            except (ValueError, KeyError):
                pass

        for entry in _income_entries.get(user_id, []):
            try:
                d = datetime.fromisoformat(entry["date"])
                if d < cutoff:
                    continue
                key = f"{d.year}-{d.month:02d}"
                if key not in result:
                    result[key] = {"spending": 0, "income": 0}
                result[key]["income"] += abs(float(entry.get("amount", 0)))
            except (ValueError, KeyError):
                pass

        return result

    def _exponential_smooth(self, series: List[float]) -> List[float]:
        if not series:
            return []
        smoothed = [series[0]]
        for val in series[1:]:
            smoothed.append(self.ALPHA * val + (1 - self.ALPHA) * smoothed[-1])
        return smoothed

    def _calc_trend(self, series: List[float]) -> float:
        if len(series) < 2:
            return 0
        n = len(series)
        x_mean = (n - 1) / 2
        y_mean = statistics.mean(series)
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(series))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        return numerator / denominator if denominator > 0 else 0

    def _generate_summary(self, forecast: List[Dict], history: Dict) -> Dict:
        if not forecast:
            return {}
        final_balance = forecast[-1]["projected_balance"]
        total_net = sum(f["projected_net"] for f in forecast)
        deficit_months = [f["month_label"] for f in forecast if f["projected_net"] < 0]

        return {
            "final_projected_balance": round(final_balance, 2),
            "total_projected_net": round(total_net, 2),
            "deficit_months": deficit_months,
            "outlook": "positive" if total_net > 0 else "negative",
            "recommendation": (
                "Cash flow is projected to be positive. Consider increasing savings."
                if total_net > 0 else
                "Cash flow is projected to be negative. Review spending or increase income."
            ),
        }