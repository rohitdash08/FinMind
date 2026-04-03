from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime, timedelta
import statistics

_transactions: Dict[str, List[Dict]] = defaultdict(list)
_budgets: Dict[str, Dict] = defaultdict(dict)  # user_id -> {category: budget_amount}

class DynamicBudgetService:
    """
    Analyzes spending history to suggest personalized budget targets.
    Suggestions are based on the 50/30/20 rule and actual spending patterns.
    """

    # 50/30/20 rule defaults
    NEEDS_RATIO = 0.50
    WANTS_RATIO = 0.30
    SAVINGS_RATIO = 0.20

    NEEDS_CATEGORIES = {"rent", "utilities", "groceries", "healthcare", "insurance", "transport"}
    WANTS_CATEGORIES = {"entertainment", "dining", "travel", "shopping", "subscriptions"}

    def suggest_budgets(self, user_id: str, monthly_income: Optional[float] = None) -> Dict[str, Any]:
        """
        Analyze 3 months of spending and suggest optimized budgets per category.
        """
        now = datetime.utcnow()
        history = []
        for i in range(1, 4):  # Last 3 months
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            history.append(self._get_month_spending(user_id, y, m))

        # Average spending per category over 3 months
        all_categories = set()
        for month_data in history:
            all_categories.update(month_data.keys())

        avg_by_category: Dict[str, float] = {}
        for cat in all_categories:
            amounts = [h.get(cat, 0) for h in history]
            avg_by_category[cat] = statistics.mean(amounts)

        total_avg = sum(avg_by_category.values())

        suggestions = []
        for cat, avg_spend in sorted(avg_by_category.items(), key=lambda x: -x[1]):
            current_budget = _budgets.get(user_id, {}).get(cat, 0)
            suggested = self._suggest_budget(cat, avg_spend, total_avg, monthly_income)

            variance = []
            for month_data in history:
                if cat in month_data:
                    variance.append(month_data[cat])
            volatility = statistics.stdev(variance) if len(variance) > 1 else 0

            suggestions.append({
                "category": cat,
                "avg_monthly_spend": round(avg_spend, 2),
                "suggested_budget": round(suggested, 2),
                "current_budget": current_budget,
                "volatility": round(volatility, 2),
                "reasoning": self._explain_suggestion(cat, avg_spend, suggested, volatility),
                "bucket": self._categorize_bucket(cat),
            })

        total_suggested = sum(s["suggested_budget"] for s in suggestions)
        summary = {
            "total_avg_spending": round(total_avg, 2),
            "total_suggested_budget": round(total_suggested, 2),
            "months_analyzed": 3,
        }
        if monthly_income:
            summary["income"] = monthly_income
            summary["suggested_savings"] = round(monthly_income - total_suggested, 2)
            summary["savings_rate_pct"] = round((monthly_income - total_suggested) / monthly_income * 100, 1)

        return {"suggestions": suggestions, "summary": summary}

    def set_budget(self, user_id: str, category: str, amount: float) -> Dict:
        if user_id not in _budgets:
            _budgets[user_id] = {}
        _budgets[user_id][category] = amount
        return {"category": category, "budget": amount, "set_at": datetime.utcnow().isoformat()}

    def get_budgets(self, user_id: str) -> Dict[str, float]:
        return dict(_budgets.get(user_id, {}))

    def check_budget_status(self, user_id: str, year: int, month: int) -> List[Dict]:
        """Compare current month spending vs set budgets."""
        current_spending = self._get_month_spending(user_id, year, month)
        budgets = _budgets.get(user_id, {})
        statuses = []
        for cat, budget in budgets.items():
            spent = current_spending.get(cat, 0)
            pct_used = (spent / budget * 100) if budget > 0 else 0
            statuses.append({
                "category": cat,
                "budget": budget,
                "spent": round(spent, 2),
                "remaining": round(budget - spent, 2),
                "pct_used": round(pct_used, 1),
                "status": "over" if pct_used > 100 else "warning" if pct_used > 80 else "ok",
            })
        return sorted(statuses, key=lambda x: -x["pct_used"])

    def _get_month_spending(self, user_id: str, year: int, month: int) -> Dict[str, float]:
        result: Dict[str, float] = defaultdict(float)
        for t in _transactions.get(user_id, []):
            try:
                d = datetime.fromisoformat(t["date"])
                if d.year == year and d.month == month:
                    result[t.get("category", "uncategorized")] += abs(float(t.get("amount", 0)))
            except (ValueError, KeyError):
                pass
        return dict(result)

    def _suggest_budget(self, category: str, avg: float, total: float, income: Optional[float]) -> float:
        if income:
            if category in self.NEEDS_CATEGORIES:
                cap = income * self.NEEDS_RATIO * (avg / max(total, 1))
            elif category in self.WANTS_CATEGORIES:
                cap = income * self.WANTS_RATIO * (avg / max(total, 1))
            else:
                cap = avg * 1.1  # Allow 10% buffer for uncategorized
            return max(cap, avg * 0.9)  # Don't suggest below 90% of avg
        return round(avg * 1.05, 2)  # Default: 5% buffer above average

    def _categorize_bucket(self, category: str) -> str:
        if category in self.NEEDS_CATEGORIES:
            return "needs"
        if category in self.WANTS_CATEGORIES:
            return "wants"
        return "other"

    def _explain_suggestion(self, cat: str, avg: float, suggested: float, volatility: float) -> str:
        parts = [f"Based on 3-month average of {avg:.2f}."]
        if volatility > avg * 0.3:
            parts.append("High variability detected; buffer added.")
        if suggested > avg:
            parts.append(f"Suggested {suggested - avg:.2f} buffer above average.")
        elif suggested < avg:
            parts.append("Consider reducing this category.")
        return " ".join(parts)