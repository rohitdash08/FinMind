"""Financial Dashboard Service.

Unified financial dashboard:
- Overview metrics (income, expense, savings, net)
- Recent transactions widget
- Budget progress bars
- Spending by category chart data
- Monthly trend data
- Goal progress
- Quick actions summary
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.dashboard")


class DashboardService:
    def __init__(self):
        self.overrides = {}  # user customization

    def get_dashboard(self, transactions: list, budgets: dict,
                       goals: list = None) -> dict:
        """Generate complete dashboard data."""
        now = datetime.utcnow()
        month_start = now.replace(day=1).isoformat()[:10]
        today = now.isoformat()[:10]

        # Current month transactions
        month_txns = [t for t in transactions if t["date"] >= month_start]

        income = sum(t["amount"] for t in month_txns if t.get("type") == "income")
        expenses = sum(t["amount"] for t in month_txns if t.get("type") == "expense")
        saved = income - expenses

        # Category breakdown
        by_category = defaultdict(float)
        for t in month_txns:
            if t.get("type") == "expense":
                by_category[t["category"]] += t["amount"]

        # Budget progress
        budget_progress = []
        for cat, budget in budgets.items():
            spent = by_category.get(cat, 0)
            budget_progress.append({
                "category": cat,
                "budget": budget,
                "spent": round(spent, 2),
                "remaining": round(budget - spent, 2),
                "percentage": round(spent / max(budget, 1) * 100, 1),
                "status": "over" if spent > budget else
                         "warning" if spent > budget * 0.8 else "good",
            })

        # Recent transactions
        sorted_txns = sorted(transactions, key=lambda x: x["date"], reverse=True)
        recent = sorted_txns[:10]

        # Monthly trend (last 6 months)
        monthly_data = []
        for i in range(5, -1, -1):
            month_date = (now - timedelta(days=i * 30)).replace(day=1)
            month_str = month_date.isoformat()[:7]
            month_txns_filtered = [
                t for t in transactions
                if t["date"].startswith(month_str)
            ]
            m_income = sum(t["amount"] for t in month_txns_filtered if t.get("type") == "income")
            m_expense = sum(t["amount"] for t in month_txns_filtered if t.get("type") == "expense")
            monthly_data.append({
                "month": month_str,
                "income": round(m_income, 2),
                "expense": round(m_expense, 2),
                "savings": round(m_income - m_expense, 2),
            })

        # Goal progress
        goal_progress = []
        if goals:
            for g in goals:
                progress = round(g.get("saved", 0) / max(g.get("target", 1), 1) * 100, 1)
                goal_progress.append({
                    "name": g.get("name", ""),
                    "target": g.get("target", 0),
                    "saved": g.get("saved", 0),
                    "progress": progress,
                    "remaining": round(g.get("target", 0) - g.get("saved", 0), 2),
                    "on_track": progress >= (now.day / max(now.day, 1) * 100 * 0.8),
                })

        # Quick stats
        days_in_month = (now.replace(month=now.month % 12 + 1, day=1) - timedelta(days=1)).day if now.month < 12 else 31
        days_passed = now.day

        return {
            "period": month_start + " to " + today,
            "overview": {
                "total_income": round(income, 2),
                "total_expenses": round(expenses, 2),
                "net_savings": round(saved, 2),
                "savings_rate": round(saved / max(income, 1) * 100, 1),
                "daily_avg_expense": round(expenses / max(days_passed, 1), 2),
                "projected_monthly_expense": round(expenses / max(days_passed, 1) * days_in_month, 2),
            },
            "recent_transactions": recent,
            "budget_progress": budget_progress,
            "spending_by_category": {
                k: round(v, 2) for k, v in
                sorted(by_category.items(), key=lambda x: x[1], reverse=True)
            },
            "monthly_trend": monthly_data,
            "goal_progress": goal_progress,
            "transaction_count": len(month_txns),
        }

    def get_quick_summary(self, transactions: list) -> dict:
        """Ultra-fast summary for widgets."""
        now = datetime.utcnow()
        today = now.isoformat()[:10]
        week_ago = (now - timedelta(days=7)).isoformat()[:10]
        month_start = now.replace(day=1).isoformat()[:10]

        today_txns = [t for t in transactions if t["date"] == today]
        week_txns = [t for t in transactions if t["date"] >= week_ago]
        month_txns = [t for t in transactions if t["date"] >= month_start]

        return {
            "today": {
                "income": round(sum(t["amount"] for t in today_txns if t.get("type") == "income"), 2),
                "expenses": round(sum(t["amount"] for t in today_txns if t.get("type") == "expense"), 2),
                "transactions": len(today_txns),
            },
            "this_week": {
                "income": round(sum(t["amount"] for t in week_txns if t.get("type") == "income"), 2),
                "expenses": round(sum(t["amount"] for t in week_txns if t.get("type") == "expense"), 2),
                "transactions": len(week_txns),
            },
            "this_month": {
                "income": round(sum(t["amount"] for t in month_txns if t.get("type") == "income"), 2),
                "expenses": round(sum(t["amount"] for t in month_txns if t.get("type") == "expense"), 2),
                "transactions": len(month_txns),
            },
        }

    def get_alerts(self, transactions: list, budgets: dict) -> list[dict]:
        """Get financial alerts for dashboard."""
        alerts = []
        now = datetime.utcnow()
        month_start = now.replace(day=1).isoformat()[:10]

        month_expenses = defaultdict(float)
        for t in transactions:
            if t["date"] >= month_start and t.get("type") == "expense":
                month_expenses[t["category"]] += t["amount"]

        # Budget warnings
        for cat, budget in budgets.items():
            spent = month_expenses.get(cat, 0)
            if spent > budget:
                alerts.append({
                    "type": "budget_exceeded",
                    "severity": "warning",
                    "category": cat,
                    "message": f"{cat} budget exceeded by ${round(spent - budget, 2)}",
                    "budget": budget,
                    "spent": round(spent, 2),
                })
            elif spent > budget * 0.8:
                alerts.append({
                    "type": "budget_warning",
                    "severity": "info",
                    "category": cat,
                    "message": f"{cat} is at {round(spent/budget*100)}% of budget",
                })

        # Unusual spending detection
        if month_expenses:
            total = sum(month_expenses.values())
            for cat, spent in month_expenses.items():
                if total > 0 and spent / total > 0.5:
                    alerts.append({
                        "type": "unusual_spending",
                        "severity": "info",
                        "category": cat,
                        "message": f"{cat} accounts for {round(spent/total*100)}% of total spending",
                    })

        return alerts
