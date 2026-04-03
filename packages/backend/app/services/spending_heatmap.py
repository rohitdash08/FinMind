from datetime import datetime, timedelta, date
from collections import defaultdict
from typing import Dict, List, Optional, Any
import calendar

# In-memory transaction store (replace with DB in production)
_transactions: Dict[str, List[Dict]] = defaultdict(list)

class SpendingHeatmapService:
    """Generates spending heatmap data for calendar visualization."""

    def monthly_heatmap(self, user_id: str, year: int, month: int,
                        category: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns day-by-day spending for a specific month.
        Output format suitable for calendar heatmap libraries (e.g., react-calendar-heatmap).
        """
        transactions = self._get_transactions(user_id, year=year, month=month, category=category)
        days_in_month = calendar.monthrange(year, month)[1]

        # Aggregate by day
        daily: Dict[int, float] = defaultdict(float)
        daily_count: Dict[int, int] = defaultdict(int)
        daily_categories: Dict[int, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        for txn in transactions:
            try:
                txn_date = datetime.fromisoformat(txn["date"]).date()
                day = txn_date.day
                amount = abs(float(txn.get("amount", 0)))
                cat = txn.get("category", "uncategorized")
                daily[day] += amount
                daily_count[day] += 1
                daily_categories[day][cat] += amount
            except (ValueError, KeyError):
                continue

        # Build heatmap data
        cells = []
        for day in range(1, days_in_month + 1):
            cells.append({
                "date": f"{year}-{month:02d}-{day:02d}",
                "day": day,
                "amount": round(daily[day], 2),
                "count": daily_count[day],
                "categories": dict(daily_categories[day]),
            })

        total = sum(daily.values())
        max_day = max(daily, key=daily.get) if daily else None
        avg_daily = total / days_in_month if days_in_month > 0 else 0

        return {
            "period": "month",
            "year": year,
            "month": month,
            "month_name": calendar.month_name[month],
            "cells": cells,
            "summary": {
                "total_spending": round(total, 2),
                "avg_daily_spending": round(avg_daily, 2),
                "peak_day": max_day,
                "peak_day_amount": round(daily[max_day], 2) if max_day else 0,
                "active_days": len(daily),
                "days_in_month": days_in_month,
            },
        }

    def yearly_heatmap(self, user_id: str, year: int,
                       category: Optional[str] = None) -> Dict[str, Any]:
        """
        Returns week-by-week spending for an entire year.
        Compatible with GitHub-style contribution heatmaps.
        """
        transactions = self._get_transactions(user_id, year=year, category=category)
        weekly: Dict[str, float] = defaultdict(float)
        monthly: Dict[int, float] = defaultdict(float)

        for txn in transactions:
            try:
                txn_date = datetime.fromisoformat(txn["date"]).date()
                if txn_date.year != year:
                    continue
                amount = abs(float(txn.get("amount", 0)))
                # ISO week
                week_str = txn_date.strftime("%Y-W%V")
                weekly[week_str] += amount
                monthly[txn_date.month] += amount
            except (ValueError, KeyError):
                continue

        # Build monthly breakdown
        months = []
        for m in range(1, 13):
            months.append({
                "month": m,
                "month_name": calendar.month_name[m],
                "amount": round(monthly[m], 2),
            })

        return {
            "period": "year",
            "year": year,
            "weekly_cells": [{"week": w, "amount": round(a, 2)} for w, a in sorted(weekly.items())],
            "monthly_breakdown": months,
            "summary": {
                "total_spending": round(sum(monthly.values()), 2),
                "peak_month": max(monthly, key=monthly.get) if monthly else None,
                "peak_month_amount": round(max(monthly.values()), 2) if monthly else 0,
            },
        }

    def peak_spending_summary(self, user_id: str, year: int, month: int) -> Dict[str, Any]:
        """Returns insights about peak spending days."""
        heatmap = self.monthly_heatmap(user_id, year=year, month=month)
        cells = sorted(heatmap["cells"], key=lambda c: c["amount"], reverse=True)
        top_days = [c for c in cells[:5] if c["amount"] > 0]

        # Weekday vs weekend breakdown
        weekday_total = 0.0
        weekend_total = 0.0
        for cell in heatmap["cells"]:
            try:
                d = date.fromisoformat(cell["date"])
                if d.weekday() >= 5:
                    weekend_total += cell["amount"]
                else:
                    weekday_total += cell["amount"]
            except ValueError:
                pass

        return {
            "top_spending_days": top_days,
            "weekday_vs_weekend": {
                "weekday_total": round(weekday_total, 2),
                "weekend_total": round(weekend_total, 2),
                "higher_on_weekends": weekend_total / 2 > weekday_total / 5 if weekday_total else False,
            },
            "month": month,
            "year": year,
        }

    def _get_transactions(self, user_id: str, year: int, month: Optional[int] = None,
                          category: Optional[str] = None) -> List[Dict]:
        txns = _transactions.get(user_id, [])
        filtered = []
        for t in txns:
            try:
                d = datetime.fromisoformat(t["date"])
                if d.year != year:
                    continue
                if month and d.month != month:
                    continue
                if category and t.get("category") != category:
                    continue
                filtered.append(t)
            except (ValueError, KeyError):
                continue
        return filtered
