from typing import Dict, List, Optional, Any
from collections import defaultdict
from datetime import datetime, timedelta
import calendar

_transactions: Dict[str, List[Dict]] = defaultdict(list)

class ExplainableInsightsService:
    """Generates human-readable explanations for spending patterns."""

    def get_insights(self, user_id: str, year: int, month: int) -> Dict[str, Any]:
        txns = self._get_month_transactions(user_id, year, month)
        prev_txns = self._get_month_transactions(user_id, *self._prev_month(year, month))

        by_category = self._group_by_category(txns)
        prev_by_category = self._group_by_category(prev_txns)
        total = sum(sum(v) for v in by_category.values())
        prev_total = sum(sum(v) for v in prev_by_category.values())

        insights = []

        # Top spending category
        if by_category:
            top_cat = max(by_category, key=lambda c: sum(by_category[c]))
            top_amount = sum(by_category[top_cat])
            pct = (top_amount / total * 100) if total > 0 else 0
            insights.append({
                "type": "top_category",
                "title": f"{top_cat} is your biggest expense",
                "description": f"You spent {top_amount:.2f} on {top_cat} this month ({pct:.0f}% of total).",
                "category": top_cat,
                "amount": round(top_amount, 2),
                "percentage": round(pct, 1),
                "severity": "info",
            })

        # Month-over-month comparison
        if prev_total > 0:
            change = ((total - prev_total) / prev_total) * 100
            if abs(change) >= 10:
                direction = "increased" if change > 0 else "decreased"
                severity = "warning" if change > 20 else "info"
                insights.append({
                    "type": "mom_change",
                    "title": f"Spending {direction} by {abs(change):.0f}% vs last month",
                    "description": f"Total this month: {total:.2f}. Last month: {prev_total:.2f}. Change: {change:+.0f}%.",
                    "amount": round(total, 2),
                    "prev_amount": round(prev_total, 2),
                    "change_pct": round(change, 1),
                    "severity": severity,
                })

        # Category spikes (>50% increase vs prior month)
        for cat, amounts in by_category.items():
            curr_sum = sum(amounts)
            prev_sum = sum(prev_by_category.get(cat, [0]))
            if prev_sum > 0:
                spike = ((curr_sum - prev_sum) / prev_sum) * 100
                if spike > 50:
                    insights.append({
                        "type": "category_spike",
                        "title": f"{cat} spending jumped {spike:.0f}%",
                        "description": f"{cat}: {curr_sum:.2f} this month vs {prev_sum:.2f} last month.",
                        "category": cat,
                        "amount": round(curr_sum, 2),
                        "prev_amount": round(prev_sum, 2),
                        "spike_pct": round(spike, 1),
                        "severity": "warning",
                    })

        # Large single transactions
        all_txns = [t for t in txns]
        for t in all_txns:
            amount = abs(float(t.get("amount", 0)))
            if amount > 200:
                insights.append({
                    "type": "large_transaction",
                    "title": f"Large {t.get('category','unknown')} transaction: {amount:.2f}",
                    "description": f"On {t.get('date','?')}, a transaction of {amount:.2f} was recorded for {t.get('category','unknown')}.",
                    "amount": round(amount, 2),
                    "date": t.get("date"),
                    "category": t.get("category"),
                    "severity": "info",
                })

        return {
            "month": month,
            "year": year,
            "total_spending": round(total, 2),
            "insights": insights,
            "category_breakdown": {cat: round(sum(v), 2) for cat, v in by_category.items()},
        }

    def _group_by_category(self, txns: List[Dict]) -> Dict[str, List[float]]:
        result: Dict[str, List[float]] = defaultdict(list)
        for t in txns:
            cat = t.get("category", "uncategorized")
            result[cat].append(abs(float(t.get("amount", 0))))
        return result

    def _get_month_transactions(self, user_id: str, year: int, month: int) -> List[Dict]:
        result = []
        for t in _transactions.get(user_id, []):
            try:
                d = datetime.fromisoformat(t["date"])
                if d.year == year and d.month == month:
                    result.append(t)
            except (ValueError, KeyError):
                pass
        return result

    def _prev_month(self, year: int, month: int):
        if month == 1:
            return year - 1, 12
        return year, month - 1