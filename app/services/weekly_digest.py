"""
Weekly Financial Summary Module
Generates weekly summaries highlighting trends and insights.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import json


@dataclass
class Transaction:
    """Financial transaction record."""
    id: str
    amount: float
    category: str
    date: datetime
    description: str
    type: str  # 'income' or 'expense'


@dataclass
class WeeklySummary:
    """Weekly financial summary."""
    week_start: datetime
    week_end: datetime
    total_income: float
    total_expense: float
    net_savings: float
    top_expenses: List[Dict[str, Any]]
    top_income_sources: List[Dict[str, Any]]
    category_breakdown: Dict[str, float]
    trends: Dict[str, Any]
    insights: List[str]


class WeeklyDigestGenerator:
    """Generates smart weekly financial digests."""
    
    def __init__(self):
        self.transactions: List[Transaction] = []
    
    def add_transaction(self, transaction: Transaction) -> None:
        """Add a transaction to the tracker."""
        self.transactions.append(transaction)
    
    def get_weekly_summary(
        self, 
        week_start: Optional[datetime] = None
    ) -> WeeklySummary:
        """Generate summary for a specific week (default: current week)."""
        if week_start is None:
            week_start = datetime.now() - timedelta(days=7)
        
        week_end = week_start + timedelta(days=7)
        
        # Filter transactions for this week
        week_transactions = [
            t for t in self.transactions 
            if week_start <= t.date < week_end
        ]
        
        # Calculate totals
        income_transactions = [t for t in week_transactions if t.type == 'income']
        expense_transactions = [t for t in week_transactions if t.type == 'expense']
        
        total_income = sum(t.amount for t in income_transactions)
        total_expense = sum(t.amount for t in expense_transactions)
        net_savings = total_income - total_expense
        
        # Top expenses
        sorted_expenses = sorted(
            expense_transactions, 
            key=lambda x: x.amount, 
            reverse=True
        )[:5]
        top_expenses = [
            {
                'description': t.description,
                'amount': t.amount,
                'category': t.category,
                'percentage': (t.amount / total_expense * 100) if total_expense > 0 else 0
            }
            for t in sorted_expenses
        ]
        
        # Top income sources
        sorted_income = sorted(
            income_transactions,
            key=lambda x: x.amount,
            reverse=True
        )[:5]
        top_income_sources = [
            {
                'description': t.description,
                'amount': t.amount,
                'category': t.category,
                'percentage': (t.amount / total_income * 100) if total_income > 0 else 0
            }
            for t in sorted_income
        ]
        
        # Category breakdown
        category_totals: Dict[str, float] = {}
        for t in expense_transactions:
            category_totals[t.category] = category_totals.get(t.category, 0) + t.amount
        
        # Generate insights
        insights = self._generate_insights(
            total_income, total_expense, net_savings, category_totals
        )
        
        # Calculate trends (compare with previous week)
        trends = self._calculate_trends(week_start)
        
        return WeeklySummary(
            week_start=week_start,
            week_end=week_end,
            total_income=total_income,
            total_expense=total_expense,
            net_savings=net_savings,
            top_expenses=top_expenses,
            top_income_sources=top_income_sources,
            category_breakdown=category_totals,
            trends=trends,
            insights=insights
        )
    
    def _generate_insights(
        self,
        total_income: float,
        total_expense: float,
        net_savings: float,
        category_totals: Dict[str, float]
    ) -> List[str]:
        """Generate personalized financial insights."""
        insights = []
        
        # Savings rate insight
        if total_income > 0:
            savings_rate = (net_savings / total_income) * 100
            if savings_rate >= 20:
                insights.append(f"🎉 Great job! You saved {savings_rate:.1f}% of your income this week.")
            elif savings_rate >= 10:
                insights.append(f"👍 Good progress! You saved {savings_rate:.1f}% of your income.")
            elif savings_rate < 0:
                insights.append("⚠️  You spent more than you earned this week. Consider reviewing your expenses.")
        
        # Top spending category
        if category_totals:
            top_category = max(category_totals.items(), key=lambda x: x[1])
            insights.append(f"💰 Your biggest expense was '{top_category[0]}' at ${top_category[1]:.2f}.")
        
        # Expense to income ratio
        if total_income > 0:
            expense_ratio = (total_expense / total_income) * 100
            if expense_ratio > 90:
                insights.append("📊 Your expenses are close to your income. Try to reduce discretionary spending.")
        
        return insights
    
    def _calculate_trends(self, current_week_start: datetime) -> Dict[str, Any]:
        """Calculate week-over-week trends."""
        prev_week_start = current_week_start - timedelta(days=7)
        prev_week_end = current_week_start
        
        # Get previous week transactions
        prev_transactions = [
            t for t in self.transactions
            if prev_week_start <= t.date < prev_week_end
        ]
        
        prev_income = sum(t.amount for t in prev_transactions if t.type == 'income')
        prev_expense = sum(t.amount for t in prev_transactions if t.type == 'expense')
        
        # Current week (recalculate for comparison)
        current_transactions = [
            t for t in self.transactions
            if current_week_start <= t.date < current_week_start + timedelta(days=7)
        ]
        
        current_income = sum(t.amount for t in current_transactions if t.type == 'income')
        current_expense = sum(t.amount for t in current_transactions if t.type == 'expense')
        
        # Calculate changes
        income_change = ((current_income - prev_income) / prev_income * 100) if prev_income > 0 else 0
        expense_change = ((current_expense - prev_expense) / prev_expense * 100) if prev_expense > 0 else 0
        
        return {
            'income_change_percent': round(income_change, 1),
            'expense_change_percent': round(expense_change, 1),
            'income_trend': 'up' if income_change > 0 else 'down' if income_change < 0 else 'stable',
            'expense_trend': 'up' if expense_change > 0 else 'down' if expense_change < 0 else 'stable'
        }
    
    def generate_digest_report(self, summary: WeeklySummary) -> str:
        """Generate a human-readable digest report."""
        report = f"""
📊 Weekly Financial Summary
Week of {summary.week_start.strftime('%Y-%m-%d')} to {summary.week_end.strftime('%Y-%m-%d')}

💵 Overview
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Income:    ${summary.total_income:,.2f}
Total Expenses:  ${summary.total_expense:,.2f}
Net Savings:     ${summary.net_savings:,.2f}

📈 Trends (vs last week)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Income:  {summary.trends['income_trend'].upper()} ({summary.trends['income_change_percent']:+.1f}%)
Expenses: {summary.trends['expense_trend'].upper()} ({summary.trends['expense_change_percent']:+.1f}%)

🔥 Top Expenses
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        for i, exp in enumerate(summary.top_expenses[:3], 1):
            report += f"{i}. {exp['description']}: ${exp['amount']:,.2f} ({exp['percentage']:.1f}%)\n"
        
        report += "\n💡 Insights\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        for insight in summary.insights:
            report += f"• {insight}\n"
        
        return report


# Example usage and tests
if __name__ == "__main__":
    # Create generator
    generator = WeeklyDigestGenerator()
    
    # Add sample transactions
    now = datetime.now()
    
    # Income
    generator.add_transaction(Transaction("1", 5000, "Salary", now - timedelta(days=1), "Monthly Salary", "income"))
    generator.add_transaction(Transaction("2", 200, "Freelance", now - timedelta(days=3), "Side project", "income"))
    
    # Expenses
    generator.add_transaction(Transaction("3", 1200, "Rent", now - timedelta(days=2), "Monthly Rent", "expense"))
    generator.add_transaction(Transaction("4", 300, "Food", now - timedelta(days=1), "Groceries", "expense"))
    generator.add_transaction(Transaction("5", 150, "Transport", now - timedelta(days=4), "Gas", "expense"))
    generator.add_transaction(Transaction("6", 80, "Entertainment", now - timedelta(days=5), "Movie", "expense"))
    
    # Generate summary
    summary = generator.get_weekly_summary()
    
    # Print report
    print(generator.generate_digest_report(summary))
    
    # Export as JSON
    print("\n📤 JSON Export:")
    print(json.dumps({
        'week_start': summary.week_start.isoformat(),
        'week_end': summary.week_end.isoformat(),
        'total_income': summary.total_income,
        'total_expense': summary.total_expense,
        'net_savings': summary.net_savings,
        'insights': summary.insights
    }, indent=2))
