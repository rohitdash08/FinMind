"""Financial Health Score Calculator.

Comprehensive financial health assessment:
- Savings rate scoring
- Debt-to-income ratio
- Emergency fund adequacy
- Spending diversity (not over-concentrated)
- Budget adherence
- Financial stability trend
- Overall composite score (0-100)
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.health")


class HealthScore:
    def __init__(self, category: str, score: float, max_score: float,
                 details: dict, recommendation: str):
        self.category = category
        self.score = score
        self.max_score = max_score
        self.details = details
        self.recommendation = recommendation

    @property
    def percentage(self) -> float:
        return round(self.score / max(self.max_score, 1) * 100, 1)

    def to_dict(self):
        return {
            "category": self.category,
            "score": round(self.score, 1),
            "max_score": self.max_score,
            "percentage": self.percentage,
            "grade": self._grade(),
            "details": self.details,
            "recommendation": self.recommendation,
        }

    def _grade(self) -> str:
        pct = self.percentage
        if pct >= 90: return "A"
        if pct >= 80: return "B"
        if pct >= 70: return "C"
        if pct >= 60: return "D"
        return "F"


class FinancialHealthService:
    """Calculate comprehensive financial health scores."""

    def calculate(self, monthly_income: float,
                   monthly_expenses: list[dict],
                   savings_balance: float = 0,
                   debt_balance: float = 0,
                   monthly_debt_payment: float = 0,
                   investment_balance: float = 0,
                   goals: list[dict] = None) -> dict:
        """Calculate overall financial health score."""

        scores = []

        # 1. Savings Rate (25 points)
        savings_score = self._score_savings_rate(monthly_income, monthly_expenses)
        scores.append(savings_score)

        # 2. Emergency Fund (20 points)
        emergency_score = self._score_emergency_fund(
            savings_balance, monthly_income, monthly_expenses)
        scores.append(emergency_score)

        # 3. Debt-to-Income (20 points)
        debt_score = self._score_debt_to_income(monthly_income, monthly_debt_payment, debt_balance)
        scores.append(debt_score)

        # 4. Spending Diversity (15 points)
        diversity_score = self._score_spending_diversity(monthly_expenses)
        scores.append(diversity_score)

        # 5. Budget Adherence (10 points)
        budget_score = self._score_budget_adherence(monthly_income, monthly_expenses)
        scores.append(budget_score)

        # 6. Investment / Wealth Building (10 points)
        investment_score = self._score_investments(
            monthly_income, investment_balance)
        scores.append(investment_score)

        # Calculate total
        total_score = sum(s.score for s in scores)
        max_total = sum(s.max_score for s in scores)

        # Generate overall grade
        overall_pct = total_score / max(max_total, 1) * 100

        return {
            "overall_score": round(total_score, 1),
            "max_score": max_total,
            "percentage": round(overall_pct, 1),
            "grade": self._overall_grade(overall_pct),
            "categories": [s.to_dict() for s in scores],
            "top_recommendations": self._top_recommendations(scores),
            "summary": self._generate_summary(overall_pct, scores),
        }

    def _score_savings_rate(self, income: float,
                             expenses: list[dict]) -> HealthScore:
        """Score savings rate (25 points max)."""
        total_spent = sum(abs(float(e.get("amount", 0)))
                         for e in expenses
                         if float(e.get("amount", 0)) < 0
                         or e.get("type", "").lower() == "expense")

        savings_rate = (income - total_spent) / max(income, 1) * 100

        # Scoring: 20%+ savings = 25/25, <5% = 5/25
        if savings_rate >= 20:
            score = 25
            rec = "Excellent savings rate! Keep it up."
        elif savings_rate >= 15:
            score = 20
            rec = "Good savings rate. Aim for 20%+"
        elif savings_rate >= 10:
            score = 15
            rec = "Moderate savings. Try to increase to 15-20%"
        elif savings_rate >= 5:
            score = 10
            rec = "Low savings rate. Reduce non-essential spending."
        else:
            score = max(savings_rate * 2, 2)
            rec = "Critical: spending exceeds income. Immediate action needed."

        return HealthScore(
            category="savings_rate",
            score=score,
            max_score=25,
            details={"savings_rate": round(savings_rate, 1),
                    "monthly_savings": round(income - total_spent, 2),
                    "monthly_spending": round(total_spent, 2)},
            recommendation=rec,
        )

    def _score_emergency_fund(self, savings: float, income: float,
                                expenses: list[dict]) -> HealthScore:
        """Score emergency fund adequacy (20 points max)."""
        total_spent = sum(abs(float(e.get("amount", 0)))
                         for e in expenses
                         if float(e.get("amount", 0)) < 0
                         or e.get("type", "").lower() == "expense")

        monthly_expense = total_spent
        months_covered = savings / max(monthly_expense, 1)

        # 6+ months = 20/20, <1 month = 2/20
        if months_covered >= 6:
            score = 20
            rec = "Strong emergency fund covering 6+ months."
        elif months_covered >= 3:
            score = 15
            rec = "Good emergency fund. Aim for 6 months of expenses."
        elif months_covered >= 1:
            score = 8
            rec = "Minimal emergency fund. Build to 3-6 months."
        else:
            score = 2
            rec = "No emergency fund. Start saving immediately."

        return HealthScore(
            category="emergency_fund",
            score=score,
            max_score=20,
            details={"savings_balance": savings,
                    "monthly_expenses": round(monthly_expense, 2),
                    "months_covered": round(months_covered, 1)},
            recommendation=rec,
        )

    def _score_debt_to_income(self, income: float, monthly_debt: float,
                                total_debt: float) -> HealthScore:
        """Score debt-to-income ratio (20 points max)."""
        dti = monthly_debt / max(income, 1) * 100

        if dti <= 10:
            score = 20
            rec = "Excellent debt management."
        elif dti <= 20:
            score = 16
            rec = "Good debt level. Keep paying down."
        elif dti <= 36:
            score = 10
            rec = "Moderate debt. Focus on high-interest debt first."
        elif dti <= 50:
            score = 5
            rec = "High debt-to-income ratio. Seek consolidation options."
        else:
            score = 2
            rec = "Critical debt level. Consider financial counseling."

        return HealthScore(
            category="debt_to_income",
            score=score,
            max_score=20,
            details={"monthly_debt_payment": monthly_debt,
                    "total_debt": total_debt,
                    "dti_ratio": round(dti, 1)},
            recommendation=rec,
        )

    def _score_spending_diversity(self, expenses: list[dict]) -> HealthScore:
        """Score spending diversity (15 points max)."""
        by_cat = defaultdict(float)
        for e in expenses:
            if float(e.get("amount", 0)) < 0 or e.get("type", "").lower() == "expense":
                cat = e.get("category", "other")
                by_cat[cat] += abs(float(e.get("amount", 0)))

        if not by_cat:
            return HealthScore("spending_diversity", 10, 15, {}, "Add expense categories")

        total = sum(by_cat.values())
        categories = len(by_cat)

        # Herfindahl index (lower = more diverse)
        hhi = sum((v / max(total, 1)) ** 2 for v in by_cat.values())

        # Many categories with even distribution = good
        if categories >= 6 and hhi < 0.2:
            score = 15
        elif categories >= 4 and hhi < 0.3:
            score = 12
        elif categories >= 3:
            score = 8
        else:
            score = 5

        return HealthScore(
            category="spending_diversity",
            score=score,
            max_score=15,
            details={"categories": categories,
                    "top_category": max(by_cat, key=by_cat.get) if by_cat else None,
                    "concentration": round(hhi, 2)},
            recommendation="Diversify spending tracking across more categories" if score < 12 else "Good category diversity",
        )

    def _score_budget_adherence(self, income: float,
                                  expenses: list[dict]) -> HealthScore:
        """Score budget adherence (10 points max)."""
        total_spent = sum(abs(float(e.get("amount", 0)))
                         for e in expenses
                         if float(e.get("amount", 0)) < 0
                         or e.get("type", "").lower() == "expense")

        utilization = total_spent / max(income, 1) * 100

        if utilization <= 80:
            score = 10
        elif utilization <= 90:
            score = 8
        elif utilization <= 100:
            score = 5
        else:
            score = 2

        return HealthScore(
            category="budget_adherence",
            score=score,
            max_score=10,
            details={"budget_utilization": round(utilization, 1)},
            recommendation="Under budget" if utilization <= 100 else "Over budget! Reduce spending.",
        )

    def _score_investments(self, income: float,
                            investment_balance: float) -> HealthScore:
        """Score investment/wealth building (10 points max)."""
        if investment_balance >= income * 12:
            score = 10
        elif investment_balance >= income * 6:
            score = 8
        elif investment_balance >= income * 3:
            score = 5
        elif investment_balance > 0:
            score = 3
        else:
            score = 0

        return HealthScore(
            category="investments",
            score=score,
            max_score=10,
            details={"investment_balance": investment_balance,
                    "months_of_income": round(investment_balance / max(income, 1), 1)},
            recommendation="Start investing for long-term wealth" if investment_balance == 0 else "Continue building investments",
        )

    def _overall_grade(self, pct: float) -> str:
        if pct >= 90: return "A"
        if pct >= 80: return "B"
        if pct >= 70: return "C"
        if pct >= 60: return "D"
        return "F"

    def _top_recommendations(self, scores: list[HealthScore]) -> list[str]:
        """Get top 3 recommendations from lowest-scoring categories."""
        sorted_scores = sorted(scores, key=lambda s: s.percentage)
        return [s.recommendation for s in sorted_scores[:3]]

    def _generate_summary(self, pct: float, scores: list) -> str:
        if pct >= 80:
            return f"Excellent financial health (score: {pct:.0f}/100). You're on track!"
        elif pct >= 60:
            return f"Good financial health (score: {pct:.0f}/100). Room for improvement."
        elif pct >= 40:
            return f"Fair financial health (score: {pct:.0f}/100). Focus on weak areas."
        else:
            return f"Needs attention (score: {pct:.0f}/100). Take action on recommendations."
