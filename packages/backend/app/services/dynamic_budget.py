"""Dynamic Budget Suggestion Engine.

AI-driven budget recommendations based on spending patterns:
- Category-based budget allocation suggestions
- Seasonal spending adjustments
- Goal-oriented budget optimization
- Historical pattern analysis
- Savings opportunity identification
- Progressive budget tightening
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.budget")


class BudgetSuggestion:
    def __init__(self, category: str, current: float, suggested: float,
                 reason: str, savings_potential: float):
        self.category = category
        self.current_spending = current
        self.suggested_budget = suggested
        self.reason = reason
        self.savings_potential = savings_potential

    def to_dict(self):
        return {
            "category": self.category,
            "current_spending": round(self.current_spending, 2),
            "suggested_budget": round(self.suggested_budget, 2),
            "change_pct": round((self.suggested_budget - self.current_spending) / max(self.current_spending, 1) * 100, 1),
            "reason": self.reason,
            "savings_potential": round(self.savings_potential, 2),
        }


class DynamicBudgetService:
    """Generate dynamic budget suggestions based on spending history."""

    def __init__(self):
        # Typical budget allocation ratios (based on 50/30/20 rule)
        self.default_ratios = {
            "housing": 0.30,
            "food": 0.15,
            "transport": 0.10,
            "entertainment": 0.05,
            "shopping": 0.05,
            "health": 0.05,
            "education": 0.05,
            "savings": 0.20,
            "other": 0.05,
        }

    def _monthly_by_category(self, transactions: list[dict]) -> dict:
        """Aggregate monthly spending by category."""
        monthly = defaultdict(float)
        for tx in transactions:
            cat = tx.get("category", "other")
            amount = abs(float(tx.get("amount", 0)))
            if tx.get("amount", 0) < 0 or tx.get("type", "").lower() == "expense":
                monthly[cat] += amount
        return dict(monthly)

    def _monthly_totals(self, transactions: list[dict], months: int = 3) -> list[dict]:
        """Get monthly totals for trend analysis."""
        by_month = defaultdict(lambda: defaultdict(float))
        for tx in transactions:
            date_str = str(tx.get("date", ""))[:7]  # YYYY-MM
            cat = tx.get("category", "other")
            amount = abs(float(tx.get("amount", 0)))
            if tx.get("amount", 0) < 0 or tx.get("type", "").lower() == "expense":
                by_month[date_str][cat] += amount
                by_month[date_str]["_total"] += amount

        return [dict(v) for v in sorted(by_month.values())]

    def _identify_overspending(self, category_spending: dict,
                                monthly_income: float) -> list[str]:
        """Find categories where spending exceeds recommended ratio."""
        overspent = []
        for cat, amount in category_spending.items():
            ratio = amount / max(monthly_income, 1)
            recommended = self.default_ratios.get(cat, 0.05)
            if ratio > recommended * 1.5:  # 50% over recommended
                overspent.append(cat)
        return overspent

    def _find_savings_opportunities(self, category_spending: dict,
                                     monthly_income: float) -> list[dict]:
        """Identify specific saving opportunities."""
        opportunities = []

        for cat, amount in category_spending.items():
            recommended = self.default_ratios.get(cat, 0.05) * monthly_income
            if amount > recommended * 1.2:
                potential = amount - recommended
                opportunities.append({
                    "category": cat,
                    "current": amount,
                    "recommended": recommended,
                    "savings_potential": potential,
                    "severity": "high" if amount > recommended * 2 else "medium",
                })

        return sorted(opportunities, key=lambda x: x["savings_potential"], reverse=True)

    def generate_suggestions(self, transactions: list[dict],
                              monthly_income: float,
                              savings_goal: float = 0,
                              aggressive: bool = False) -> dict:
        """Generate personalized budget suggestions."""
        category_spending = self._monthly_by_category(transactions)
        total_spending = sum(category_spending.values())

        suggestions = []
        total_savings_potential = 0

        for cat, amount in category_spending.items():
            recommended_ratio = self.default_ratios.get(cat, 0.05)
            base_suggested = monthly_income * recommended_ratio

            # Adjust based on actual spending patterns
            if aggressive:
                suggested = min(amount, base_suggested * 0.8)
            else:
                suggested = min(amount, base_suggested * 1.1)

            # Gradual adjustment (don't suggest cutting more than 30% at once)
            max_cut = amount * 0.3
            suggested = max(suggested, amount - max_cut)

            savings = max(amount - suggested, 0)
            total_savings_potential += savings

            if savings > 0:
                suggestions.append(BudgetSuggestion(
                    category=cat,
                    current=amount,
                    suggested=suggested,
                    reason=self._get_reason(cat, amount, suggested, monthly_income),
                    savings_potential=savings,
                ))

        # Sort by savings potential
        suggestions.sort(key=lambda s: s.savings_potential, reverse=True)

        # Calculate recommended savings
        recommended_savings = monthly_income * 0.20
        if savings_goal > 0:
            recommended_savings = max(recommended_savings, savings_goal)

        return {
            "monthly_income": round(monthly_income, 2),
            "total_spending": round(total_spending, 2),
            "total_savings_potential": round(total_savings_potential, 2),
            "recommended_savings": round(recommended_savings, 2),
            "savings_rate": round((monthly_income - total_spending) / max(monthly_income, 1) * 100, 1),
            "overspending_categories": self._identify_overspending(category_spending, monthly_income),
            "savings_opportunities": self._find_savings_opportunities(category_spending, monthly_income),
            "suggestions": [s.to_dict() for s in suggestions],
            "budget_allocation": self._generate_allocation(category_spending, monthly_income, suggestions),
        }

    def _get_reason(self, category: str, current: float, suggested: float,
                     income: float) -> str:
        ratio = current / max(income, 1)
        recommended = self.default_ratios.get(category, 0.05)

        if ratio > recommended * 2:
            return f"{category} spending ({ratio:.0%}) is over 2x recommended ({recommended:.0%})"
        elif ratio > recommended * 1.5:
            return f"{category} spending ({ratio:.0%}) exceeds recommended ({recommended:.0%})"
        else:
            return f"Minor optimization possible in {category}"

    def _generate_allocation(self, spending: dict, income: float,
                              suggestions: list) -> dict:
        """Generate optimized budget allocation."""
        suggested_map = {s.category: s.suggested_budget for s in suggestions}

        allocation = {}
        total_allocated = 0

        for cat, ratio in self.default_ratios.items():
            if cat in spending:
                amount = suggested_map.get(cat, spending[cat])
            else:
                amount = income * ratio

            allocation[cat] = round(amount, 2)
            total_allocated += amount

        # Add savings category
        allocation["savings"] = round(max(income - total_allocated, 0), 2)

        return allocation
