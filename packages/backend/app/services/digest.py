from datetime import datetime, timedelta
from sqlalchemy import extract, func
from ..extensions import db
from ..models import Expense, Category
from .ai import _gemini_budget_suggestion

class SmartDigestService:
    @staticmethod
    def get_weekly_summary(user_id: int):
        """
        Generates a smart financial summary for the last 7 days.
        """
        today = datetime.utcnow().date()
        seven_days_ago = today - timedelta(days=7)
        fourteen_days_ago = today - timedelta(days=14)

        # 1. Fetch current week expenses
        current_week_expenses = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == user_id,
            Expense.spent_at >= seven_days_ago,
            Expense.spent_at <= today,
            Expense.expense_type != "INCOME"
        ).scalar()

        # 2. Fetch previous week expenses for comparison
        prev_week_expenses = db.session.query(
            func.coalesce(func.sum(Expense.amount), 0)
        ).filter(
            Expense.user_id == user_id,
            Expense.spent_at >= fourteen_days_ago,
            Expense.spent_at < seven_days_ago,
            Expense.expense_type != "INCOME"
        ).scalar()

        # 3. Get top spending category
        top_cat_row = db.session.query(
            Category.name, func.sum(Expense.amount).label("total")
        ).join(Expense, Expense.category_id == Category.id).filter(
            Expense.user_id == user_id,
            Expense.spent_at >= seven_days_ago,
            Expense.spent_at <= today
        ).group_by(Category.name).order_by(func.sum(Expense.amount).desc()).first()

        top_category = top_cat_row[0] if top_cat_row else "Uncategorized"
        top_amount = float(top_cat_row[1]) if top_cat_row else 0.0

        # 4. Calculate change percentage
        change_pct = 0.0
        if prev_week_expenses > 0:
            change_pct = float(((current_week_expenses - prev_week_expenses) / prev_week_expenses) * 100)

        # 5. Generate AI Insight (Simulated or using existing AI service)
        insight = f"Your spending this week is {'up' if change_pct > 0 else 'down'} by {abs(change_pct):.1f}% compared to last week. Your biggest expense was {top_category} at {top_amount}."

        return {
            "user_id": user_id,
            "period": "Last 7 Days",
            "total_spent": float(current_week_expenses),
            "previous_period_spent": float(prev_week_expenses),
            "change_percentage": round(change_pct, 2),
            "top_category": top_category,
            "ai_insight": insight
        }
