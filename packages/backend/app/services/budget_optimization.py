from __future__ import annotations

import statistics
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func

from app.models import Transaction
from app import db


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BudgetReallocation:
    from_category: str
    to_category: str           # "savings" if no specific target
    suggested_amount: float
    reason: str


@dataclass
class CategoryRecommendation:
    category: str
    current_avg: float          # avg monthly spend (last 3 months)
    suggested_budget: float
    potential_saving: float     # positive = can save this amount
    overspending: bool
    recommendation: str
    priority: str               # "high", "medium", "low"


@dataclass
class BudgetOptimizationResult:
    total_monthly_avg: float
    total_suggested_budget: float
    total_potential_savings: float
    recommendations: list[CategoryRecommendation]
    reallocations: list[BudgetReallocation]
    summary: str
    months_analyzed: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_monthly_category_data(user_id: int, months_back: int = 6) -> dict[str, list[float]]:
    """Return {category: [monthly_amounts...]} for the past N months."""
    cutoff = date.today() - timedelta(days=months_back * 31)
    rows = (
        db.session.query(
            func.strftime("%Y-%m", Transaction.date).label("month"),
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
        )
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.type == "expense",
        )
        .group_by("month", Transaction.category)
        .all()
    )

    # Collect months in range
    cat_by_month: dict[str, dict[str, float]] = {}
    all_months: set[str] = set()
    for row in rows:
        m = row.month
        cat = row.category or "Uncategorized"
        all_months.add(m)
        if cat not in cat_by_month:
            cat_by_month[cat] = {}
        cat_by_month[cat][m] = float(row.total or 0)

    # Convert to list per category (pad missing months with 0)
    result: dict[str, list[float]] = {}
    for cat, month_map in cat_by_month.items():
        result[cat] = [month_map.get(m, 0.0) for m in sorted(all_months)]

    return result, len(all_months)


def _classify_category(category: str) -> str:
    """Classify a category as essential, lifestyle, or discretionary."""
    essential_keywords = {"rent", "mortgage", "utilities", "insurance", "groceries",
                          "medical", "health", "transport", "fuel", "pharmacy"}
    lifestyle_keywords = {"dining", "restaurant", "coffee", "gym", "fitness",
                          "subscription", "streaming", "entertainment", "clothing"}

    cat_lower = category.lower()
    if any(k in cat_lower for k in essential_keywords):
        return "essential"
    if any(k in cat_lower for k in lifestyle_keywords):
        return "lifestyle"
    return "discretionary"


def get_budget_optimization(
    user_id: int,
    months: int = 3,
) -> BudgetOptimizationResult:
    """
    Analyze spending patterns and suggest optimal budget allocations.
    Detects overspending patterns and recommends reallocations.
    """
    months = max(1, min(12, months))

    cat_data, n_months = _get_monthly_category_data(user_id, months_back=months)

    if not cat_data:
        return BudgetOptimizationResult(
            total_monthly_avg=0.0,
            total_suggested_budget=0.0,
            total_potential_savings=0.0,
            recommendations=[],
            reallocations=[],
            summary="No spending data available for optimization.",
            months_analyzed=0,
        )

    recommendations: list[CategoryRecommendation] = []
    total_avg = 0.0
    total_suggested = 0.0

    for cat, amounts in cat_data.items():
        if not amounts:
            continue
        avg = statistics.mean(amounts)
        total_avg += avg

        # Trend: is spending growing?
        if len(amounts) >= 3:
            recent_avg = statistics.mean(amounts[-2:])
            is_growing = recent_avg > avg * 1.1
        else:
            recent_avg = amounts[-1] if amounts else avg
            is_growing = False

        cat_type = _classify_category(cat)

        # Suggest budget based on category type
        if cat_type == "essential":
            # Essential: keep as-is, no reduction recommendation
            suggested = round(avg, 2)
            potential_saving = 0.0
            overspending = False
            rec = f"{cat} is an essential expense. Budget ${suggested:.2f}/month."
            priority = "low"
        elif cat_type == "lifestyle":
            # Lifestyle: suggest 15% reduction if spending is consistent
            if is_growing:
                suggested = round(avg * 0.80, 2)
                potential_saving = round(avg - suggested, 2)
                overspending = True
                rec = (
                    f"{cat} spending is growing. Consider reducing to ${suggested:.2f}/month "
                    f"(currently ~${avg:.2f}, saving ${potential_saving:.2f})."
                )
                priority = "high"
            else:
                suggested = round(avg * 0.85, 2)
                potential_saving = round(avg - suggested, 2)
                overspending = False
                rec = (
                    f"Reducing {cat} by 15% could save ${potential_saving:.2f}/month. "
                    f"Target: ${suggested:.2f}/month."
                )
                priority = "medium"
        else:
            # Discretionary: suggest 25% reduction
            suggested = round(avg * 0.75, 2)
            potential_saving = round(avg - suggested, 2)
            overspending = is_growing
            if is_growing:
                rec = (
                    f"{cat} is a discretionary expense that is increasing. "
                    f"Cutting to ${suggested:.2f}/month could save ${potential_saving:.2f}."
                )
                priority = "high"
            else:
                rec = (
                    f"{cat} is discretionary. Reducing to ${suggested:.2f}/month "
                    f"could free up ${potential_saving:.2f}/month."
                )
                priority = "medium" if potential_saving > 20 else "low"

        total_suggested += suggested
        recommendations.append(
            CategoryRecommendation(
                category=cat,
                current_avg=round(avg, 2),
                suggested_budget=suggested,
                potential_saving=potential_saving,
                overspending=overspending,
                recommendation=rec,
                priority=priority,
            )
        )

    # Sort: high priority first, then by potential saving descending
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(
        key=lambda r: (priority_order.get(r.priority, 3), -r.potential_saving)
    )

    total_potential_savings = round(
        sum(r.potential_saving for r in recommendations), 2
    )
    total_suggested = round(total_suggested, 2)
    total_avg = round(total_avg, 2)

    # Build reallocations for top savings candidates
    reallocations: list[BudgetReallocation] = []
    top_savers = [r for r in recommendations if r.potential_saving > 0][:3]
    for saver in top_savers:
        reallocations.append(
            BudgetReallocation(
                from_category=saver.category,
                to_category="savings",
                suggested_amount=saver.potential_saving,
                reason=f"Redirecting {saver.category} savings to emergency fund or investments.",
            )
        )

    # Summary
    if total_potential_savings == 0:
        summary = "Your spending looks well-optimized. No significant reductions recommended."
    elif total_potential_savings < 50:
        summary = (
            f"Minor optimizations possible. You could save up to ${total_potential_savings:.2f}/month "
            f"with small adjustments."
        )
    else:
        summary = (
            f"Optimization opportunity: ${total_potential_savings:.2f}/month in potential savings "
            f"identified across {len([r for r in recommendations if r.potential_saving > 0])} categories."
        )

    return BudgetOptimizationResult(
        total_monthly_avg=total_avg,
        total_suggested_budget=total_suggested,
        total_potential_savings=total_potential_savings,
        recommendations=recommendations,
        reallocations=reallocations,
        summary=summary,
        months_analyzed=n_months,
    )