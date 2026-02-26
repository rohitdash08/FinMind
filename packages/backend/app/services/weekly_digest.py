"""Smart digest – weekly financial summary generator.

Produces a structured weekly summary including:
- Income vs expense totals
- Category-level breakdown
- Week-over-week trend analysis
- Budget execution status
- Actionable recommendations
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func

from ..extensions import db
from ..models import Expense, Category

logger = logging.getLogger("finmind.digest")


@dataclass
class CategorySummary:
    category_id: Optional[int]
    category_name: str
    total: float
    count: int
    pct_of_total: float = 0.0


@dataclass
class WeeklyDigest:
    user_id: int
    week_start: str
    week_end: str
    currency: str
    total_income: float
    total_expenses: float
    net_savings: float
    category_breakdown: list[CategorySummary] = field(default_factory=list)
    prev_week_expenses: Optional[float] = None
    expense_trend_pct: Optional[float] = None
    prev_week_income: Optional[float] = None
    income_trend_pct: Optional[float] = None
    top_spending_category: Optional[str] = None
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


class DigestGenerator:
    """Generates weekly financial summaries for a given user."""

    def generate(
        self,
        user_id: int,
        reference_date: Optional[date] = None,
        currency: str = "INR",
    ) -> WeeklyDigest:
        ref = reference_date or date.today()
        week_start = ref - timedelta(days=ref.weekday())  # Monday
        week_end = week_start + timedelta(days=6)  # Sunday
        prev_start = week_start - timedelta(days=7)
        prev_end = week_start - timedelta(days=1)

        # Current week totals
        income = self._sum_by_type(user_id, "INCOME", week_start, week_end)
        expenses = self._sum_by_type(user_id, "EXPENSE", week_start, week_end)

        # Previous week totals for trend
        prev_income = self._sum_by_type(user_id, "INCOME", prev_start, prev_end)
        prev_expenses = self._sum_by_type(user_id, "EXPENSE", prev_start, prev_end)

        # Category breakdown
        categories = self._category_breakdown(user_id, week_start, week_end)

        # Trends
        expense_trend = self._calc_trend(prev_expenses, expenses)
        income_trend = self._calc_trend(prev_income, income)

        # Top spending category
        top_cat = categories[0].category_name if categories else None

        # Recommendations
        recs = self._generate_recommendations(
            income, expenses, prev_expenses, expense_trend, categories
        )

        digest = WeeklyDigest(
            user_id=user_id,
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            currency=currency,
            total_income=income,
            total_expenses=expenses,
            net_savings=income - expenses,
            category_breakdown=categories,
            prev_week_expenses=prev_expenses,
            expense_trend_pct=expense_trend,
            prev_week_income=prev_income,
            income_trend_pct=income_trend,
            top_spending_category=top_cat,
            recommendations=recs,
        )
        logger.info(
            "Generated digest user_id=%s week=%s income=%.2f expenses=%.2f",
            user_id, week_start, income, expenses,
        )
        return digest

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _sum_by_type(
        user_id: int, expense_type: str, start: date, end: date
    ) -> float:
        result = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(
                Expense.user_id == user_id,
                Expense.expense_type == expense_type,
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .scalar()
        )
        return float(result or 0)

    @staticmethod
    def _category_breakdown(
        user_id: int, start: date, end: date
    ) -> list[CategorySummary]:
        rows = (
            db.session.query(
                Expense.category_id,
                func.coalesce(Category.name, "Uncategorized").label("cat_name"),
                func.sum(Expense.amount).label("total"),
                func.count(Expense.id).label("cnt"),
            )
            .outerjoin(Category, Expense.category_id == Category.id)
            .filter(
                Expense.user_id == user_id,
                Expense.expense_type == "EXPENSE",
                Expense.spent_at >= start,
                Expense.spent_at <= end,
            )
            .group_by(Expense.category_id, "cat_name")
            .order_by(func.sum(Expense.amount).desc())
            .all()
        )
        grand_total = sum(float(r.total) for r in rows) or 1.0
        return [
            CategorySummary(
                category_id=r.category_id,
                category_name=r.cat_name,
                total=float(r.total),
                count=r.cnt,
                pct_of_total=round(float(r.total) / grand_total * 100, 1),
            )
            for r in rows
        ]

    @staticmethod
    def _calc_trend(previous: float, current: float) -> Optional[float]:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    @staticmethod
    def _generate_recommendations(
        income: float,
        expenses: float,
        prev_expenses: float,
        expense_trend: Optional[float],
        categories: list[CategorySummary],
    ) -> list[str]:
        recs: list[str] = []

        if expenses > income and income > 0:
            recs.append(
                "Your expenses exceeded income this week. "
                "Consider reviewing discretionary spending."
            )

        if expense_trend is not None and expense_trend > 20:
            recs.append(
                f"Spending increased {expense_trend:.0f}% vs last week. "
                "Check if any large one-time purchases are skewing the trend."
            )

        if expense_trend is not None and expense_trend < -10:
            recs.append(
                f"Great job! Spending decreased {abs(expense_trend):.0f}% "
                "compared to last week."
            )

        if categories and categories[0].pct_of_total > 50:
            recs.append(
                f"'{categories[0].category_name}' accounts for "
                f"{categories[0].pct_of_total:.0f}% of your spending. "
                "Diversifying expenses may improve financial health."
            )

        if income > 0 and expenses <= income * 0.5:
            recs.append(
                "You saved over 50% of your income this week — excellent!"
            )

        if not recs:
            recs.append("Your finances look balanced this week. Keep it up!")

        return recs
