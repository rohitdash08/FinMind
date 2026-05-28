"""Financial Reports Generator.

Professional report generation:
- Income vs Expense reports
- Category breakdown
- Monthly/Quarterly/Yearly trends
- Budget vs Actual analysis
- Savings rate tracking
- Net worth progression
- Custom date range reports
- Export to multiple formats
"""

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.reports")


class ReportPeriod(str, Enum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    CUSTOM = "custom"


class ReportType(str, Enum):
    INCOME_EXPENSE = "income_expense"
    CATEGORY = "category"
    TREND = "trend"
    BUDGET_VS_ACTUAL = "budget_vs_actual"
    SAVINGS = "savings"
    NET_WORTH = "net_worth"
    SUMMARY = "summary"


class FinancialReport:
    def __init__(self, report_id: str, report_type: str, period: str,
                 start_date: str, end_date: str, data: dict):
        self.report_id = report_id
        self.report_type = report_type
        self.period = period
        self.start_date = start_date
        self.end_date = end_date
        self.data = data
        self.generated_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "report_type": self.report_type,
            "period": self.period,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "data": self.data,
            "generated_at": self.generated_at,
        }


class ReportGeneratorService:
    """Generate financial reports."""

    def __init__(self):
        self.reports = {}  # report_id -> FinancialReport
        self.user_reports = defaultdict(list)
        self.transactions = defaultdict(list)
        self.budgets = defaultdict(dict)  # user_id -> {category: budget_amount}

    def add_transaction(self, user_id: str, amount: float, category: str,
                         date: str, t_type: str = "expense",
                         description: str = "") -> dict:
        """Add a transaction for reporting."""
        txn = {
            "id": str(uuid4())[:8],
            "amount": round(amount, 2),
            "category": category,
            "date": date,
            "type": t_type,  # income or expense
            "description": description,
        }
        self.transactions[user_id].append(txn)
        return txn

    def set_budget(self, user_id: str, category: str, amount: float):
        """Set budget for a category."""
        self.budgets[user_id][category] = round(amount, 2)

    def generate_report(self, user_id: str, report_type: str,
                         period: str = "monthly",
                         start_date: str = None,
                         end_date: str = None) -> dict:
        """Generate a financial report."""
        now = datetime.utcnow()

        if not start_date or not end_date:
            start_date, end_date = self._get_period_dates(period, now)
            if period == "custom":
                return {"error": "Custom period requires start_date and end_date"}

        transactions = [
            t for t in self.transactions.get(user_id, [])
            if start_date <= t["date"] <= end_date
        ]

        report_id = str(uuid4())[:8]
        data = {}

        if report_type == "income_expense":
            data = self._income_expense_report(transactions)
        elif report_type == "category":
            data = self._category_report(transactions)
        elif report_type == "trend":
            data = self._trend_report(user_id, start_date, end_date)
        elif report_type == "budget_vs_actual":
            data = self._budget_vs_actual(user_id, transactions)
        elif report_type == "savings":
            data = self._savings_report(transactions)
        elif report_type == "net_worth":
            data = self._net_worth_report(transactions)
        elif report_type == "summary":
            data = self._summary_report(transactions, start_date, end_date)
        else:
            return {"error": f"Unknown report type: {report_type}"}

        report = FinancialReport(
            report_id=report_id, report_type=report_type,
            period=period, start_date=start_date, end_date=end_date,
            data=data,
        )

        self.reports[report_id] = report
        self.user_reports[user_id].append(report_id)

        return report.to_dict()

    def _income_expense_report(self, transactions: list) -> dict:
        total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")

        income_by_month = defaultdict(float)
        expense_by_month = defaultdict(float)

        for t in transactions:
            month = t["date"][:7]  # YYYY-MM
            if t["type"] == "income":
                income_by_month[month] += t["amount"]
            else:
                expense_by_month[month] += t["amount"]

        all_months = sorted(set(list(income_by_month.keys()) + list(expense_by_month.keys())))

        return {
            "total_income": round(total_income, 2),
            "total_expense": round(total_expense, 2),
            "net": round(total_income - total_expense, 2),
            "savings_rate": round(
                (total_income - total_expense) / max(total_income, 1) * 100, 1
            ),
            "monthly_breakdown": [
                {
                    "month": m,
                    "income": round(income_by_month.get(m, 0), 2),
                    "expense": round(expense_by_month.get(m, 0), 2),
                    "net": round(income_by_month.get(m, 0) - expense_by_month.get(m, 0), 2),
                }
                for m in all_months
            ],
        }

    def _category_report(self, transactions: list) -> dict:
        by_category = defaultdict(lambda: {"total": 0, "count": 0, "type": ""})

        for t in transactions:
            cat = t["category"]
            by_category[cat]["total"] += t["amount"]
            by_category[cat]["count"] += 1
            by_category[cat]["type"] = t["type"]

        total = sum(v["total"] for v in by_category.values())

        sorted_cats = sorted(by_category.items(), key=lambda x: x[1]["total"], reverse=True)

        return {
            "total_transactions": len(transactions),
            "total_amount": round(total, 2),
            "categories": [
                {
                    "category": cat,
                    "total": round(data["total"], 2),
                    "count": data["count"],
                    "percentage": round(data["total"] / max(total, 1) * 100, 1),
                    "type": data["type"],
                }
                for cat, data in sorted_cats
            ],
        }

    def _trend_report(self, user_id: str, start_date: str,
                       end_date: str) -> dict:
        """Spending trend over time."""
        txns = self.transactions.get(user_id, [])
        monthly = defaultdict(lambda: {"income": 0, "expense": 0, "count": 0})

        for t in txns:
            if start_date <= t["date"] <= end_date:
                month = t["date"][:7]
                monthly[month][t["type"]] += t["amount"]
                monthly[month]["count"] += 1

        months = sorted(monthly.keys())
        expenses = [round(monthly[m]["expense"], 2) for m in months]

        # Calculate trend (simple linear regression slope)
        if len(expenses) >= 2:
            n = len(expenses)
            x_mean = (n - 1) / 2
            y_mean = sum(expenses) / n
            numerator = sum((i - x_mean) * (e - y_mean) for i, e in enumerate(expenses))
            denominator = sum((i - x_mean) ** 2 for i in range(n))
            trend_slope = numerator / max(denominator, 0.001)
        else:
            trend_slope = 0

        return {
            "months": months,
            "monthly_expenses": expenses,
            "monthly_income": [round(monthly[m]["income"], 2) for m in months],
            "trend_direction": "increasing" if trend_slope > 0 else
                              "decreasing" if trend_slope < 0 else "stable",
            "trend_slope": round(trend_slope, 2),
            "avg_monthly_expense": round(sum(expenses) / max(len(expenses), 1), 2),
        }

    def _budget_vs_actual(self, user_id: str, transactions: list) -> dict:
        budgets = self.budgets.get(user_id, {})
        actual = defaultdict(float)

        for t in transactions:
            if t["type"] == "expense":
                actual[t["category"]] += t["amount"]

        all_cats = set(list(budgets.keys()) + list(actual.keys()))

        comparison = []
        total_budget = 0
        total_actual = 0

        for cat in all_cats:
            budget = budgets.get(cat, 0)
            spent = round(actual.get(cat, 0), 2)
            diff = round(budget - spent, 2)
            pct = round(spent / max(budget, 1) * 100, 1)

            total_budget += budget
            total_actual += spent

            comparison.append({
                "category": cat,
                "budget": budget,
                "actual": spent,
                "difference": diff,
                "usage_percentage": pct,
                "status": "over" if spent > budget else "under" if spent < budget * 0.8 else "on_track",
            })

        return {
            "total_budget": round(total_budget, 2),
            "total_actual": round(total_actual, 2),
            "total_difference": round(total_budget - total_actual, 2),
            "categories": sorted(comparison, key=lambda x: abs(x["difference"]), reverse=True),
        }

    def _savings_report(self, transactions: list) -> dict:
        income = sum(t["amount"] for t in transactions if t["type"] == "income")
        expenses = sum(t["amount"] for t in transactions if t["type"] == "expense")
        saved = income - expenses
        rate = round(saved / max(income, 1) * 100, 1)

        # Determine savings health
        if rate >= 30:
            health = "excellent"
        elif rate >= 20:
            health = "good"
        elif rate >= 10:
            health = "fair"
        elif rate >= 0:
            health = "poor"
        else:
            health = "negative"

        return {
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "total_saved": round(saved, 2),
            "savings_rate": rate,
            "savings_health": health,
            "recommended_savings": round(income * 0.2, 2),  # 20% rule
            "projected_annual_savings": round(saved * 12, 2),
        }

    def _net_worth_report(self, transactions: list) -> dict:
        """Simple net worth based on income minus expenses."""
        total_income = sum(t["amount"] for t in transactions if t["type"] == "income")
        total_expense = sum(t["amount"] for t in transactions if t["type"] == "expense")

        return {
            "period_income": round(total_income, 2),
            "period_expenses": round(total_expense, 2),
            "period_change": round(total_income - total_expense, 2),
            "note": "Net worth tracking requires asset/liability data",
        }

    def _summary_report(self, transactions: list,
                          start_date: str, end_date: str) -> dict:
        income = sum(t["amount"] for t in transactions if t["type"] == "income")
        expenses = sum(t["amount"] for t in transactions if t["type"] == "expense")
        by_cat = defaultdict(float)
        for t in transactions:
            if t["type"] == "expense":
                by_cat[t["category"]] += t["amount"]

        return {
            "period": f"{start_date} to {end_date}",
            "total_transactions": len(transactions),
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net_cash_flow": round(income - expenses, 2),
            "top_expense_categories": {
                k: round(v, 2) for k, v in
                sorted(by_cat.items(), key=lambda x: x[1], reverse=True)[:5]
            },
            "avg_daily_expense": round(expenses / max(
                (datetime.fromisoformat(end_date) -
                 datetime.fromisoformat(start_date)).days + 1, 1
            ), 2),
        }

    def get_report(self, report_id: str) -> dict:
        if report_id not in self.reports:
            return {"error": "Report not found"}
        return self.reports[report_id].to_dict()

    def get_all_reports(self, user_id: str) -> list[dict]:
        rids = self.user_reports.get(user_id, [])
        return [self.reports[rid].to_dict() for rid in rids if rid in self.reports]

    def _get_period_dates(self, period: str, now: datetime) -> tuple:
        if period == "weekly":
            start = (now - timedelta(days=7)).isoformat()[:10]
        elif period == "monthly":
            start = now.replace(day=1).isoformat()[:10]
        elif period == "quarterly":
            quarter_start_month = ((now.month - 1) // 3) * 3 + 1
            start = now.replace(month=quarter_start_month, day=1).isoformat()[:10]
        elif period == "yearly":
            start = now.replace(month=1, day=1).isoformat()[:10]
        else:
            start = (now - timedelta(days=30)).isoformat()[:10]

        return start, now.isoformat()[:10]
