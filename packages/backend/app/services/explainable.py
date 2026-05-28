"""Explainable Spending Insights for FinMind.

Provides AI-powered explanations for WHY spending changed:
- What changed (category, merchant, frequency)
- Why it changed (seasonal, new expense, price increase)
- Confidence level (high/medium/low)

Uses statistical analysis rather than external AI APIs.
"""

import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.explainable")


class SpendingInsight:
    """A single explainable insight about spending changes."""

    def __init__(self, what_changed: str, why: str, confidence: str,
                 details: dict = None, category: str = None,
                 amount_change: float = 0, percentage_change: float = 0):
        self.what_changed = what_changed
        self.why = why
        self.confidence = confidence  # high, medium, low
        self.details = details or {}
        self.category = category
        self.amount_change = amount_change
        self.percentage_change = percentage_change

    def to_dict(self):
        return {
            "what_changed": self.what_changed,
            "why": self.why,
            "confidence": self.confidence,
            "details": self.details,
            "category": self.category,
            "amount_change": round(self.amount_change, 2),
            "percentage_change": round(self.percentage_change, 1),
        }


def _group_by_category(transactions: list[dict]) -> dict[str, list]:
    """Group transactions by category."""
    groups = defaultdict(list)
    for tx in transactions:
        cat = tx.get("category", "uncategorized")
        groups[cat].append(float(tx.get("amount", 0)))
    return dict(groups)


def _group_by_merchant(transactions: list[dict]) -> dict[str, list]:
    """Group transactions by merchant."""
    groups = defaultdict(list)
    for tx in transactions:
        merchant = tx.get("merchant", "unknown").lower().strip()
        groups[merchant].append(float(tx.get("amount", 0)))
    return dict(groups)


def _calc_change(current: float, previous: float) -> tuple[float, float]:
    """Calculate absolute and percentage change."""
    abs_change = current - previous
    pct_change = ((current - previous) / previous * 100) if previous else 0
    return abs_change, pct_change


def _determine_confidence(pct_change: float, count: int) -> str:
    """Determine confidence level based on data strength."""
    if count >= 5 and abs(pct_change) > 20:
        return "high"
    elif count >= 3 and abs(pct_change) > 10:
        return "medium"
    return "low"


def generate_insights(
    current_transactions: list[dict],
    previous_transactions: list[dict],
    period_label: str = "this period",
) -> list[SpendingInsight]:
    """Generate explainable spending insights by comparing two periods.

    Args:
        current_transactions: Transactions from the current period
        previous_transactions: Transactions from the previous period
        period_label: Label for the current period (e.g., "this month")

    Returns:
        List of SpendingInsight objects explaining changes
    """
    insights = []

    # === Category-level analysis ===
    curr_cats = _group_by_category(current_transactions)
    prev_cats = _group_by_category(previous_transactions)
    all_cats = set(list(curr_cats.keys()) + list(prev_cats.keys()))

    for cat in all_cats:
        curr_total = sum(curr_cats.get(cat, []))
        prev_total = sum(prev_cats.get(cat, []))
        curr_count = len(curr_cats.get(cat, []))
        prev_count = len(prev_cats.get(cat, []))

        abs_change, pct_change = _calc_change(curr_total, prev_total)

        # Skip small changes
        if abs(pct_change) < 5 and abs(abs_change) < 10:
            continue

        confidence = _determine_confidence(pct_change, max(curr_count, prev_count))

        if prev_total == 0 and curr_total > 0:
            what = f"New spending in {cat}: ${curr_total:.2f}"
            why = f"You started spending in the '{cat}' category {period_label} with {curr_count} transactions"
            insights.append(SpendingInsight(
                what_changed=what, why=why, confidence="medium",
                category=cat, amount_change=curr_total,
                percentage_change=100, details={"new_count": curr_count}
            ))
        elif curr_total == 0 and prev_total > 0:
            what = f"Stopped spending in {cat}"
            why = f"No {cat} expenses {period_label} (previously ${prev_total:.2f})"
            insights.append(SpendingInsight(
                what_changed=what, why=why, confidence="medium",
                category=cat, amount_change=-prev_total,
                percentage_change=-100, details={"previous_count": prev_count}
            ))
        elif abs_change > 0:
            avg_price_change = abs_change / max(curr_count, 1)
            if curr_count > prev_count * 1.3:
                why = f"More frequent {cat} purchases: {curr_count} vs {prev_count} transactions"
            elif avg_price_change > prev_total / max(prev_count, 1) * 0.2:
                why = f"Higher per-transaction cost in {cat} (avg ${curr_total/max(curr_count,1):.2f} vs ${prev_total/max(prev_count,1):.2f})"
            else:
                why = f"{cat} spending increased by ${abs_change:.2f} ({pct_change:.0f}%)"

            insights.append(SpendingInsight(
                what_changed=f"{cat} spending increased: ${curr_total:.2f} vs ${prev_total:.2f}",
                why=why, confidence=confidence, category=cat,
                amount_change=abs_change, percentage_change=pct_change,
                details={"current_count": curr_count, "previous_count": prev_count}
            ))
        elif abs_change < 0:
            insights.append(SpendingInsight(
                what_changed=f"{cat} spending decreased: ${curr_total:.2f} vs ${prev_total:.2f}",
                why=f"{cat} spending dropped by ${abs(abs_change):.2f} ({abs(pct_change):.0f}%)",
                confidence=confidence, category=cat,
                amount_change=abs_change, percentage_change=pct_change,
            ))

    # === Merchant-level analysis (top changes) ===
    curr_merchants = _group_by_merchant(current_transactions)
    prev_merchants = _group_by_merchant(previous_transactions)

    # Find merchants with biggest changes
    merchant_changes = []
    for merchant in set(list(curr_merchants.keys()) + list(prev_merchants.keys())):
        curr_total = sum(curr_merchants.get(merchant, []))
        prev_total = sum(prev_merchants.get(merchant, []))
        abs_change, pct_change = _calc_change(curr_total, prev_total)
        if abs(abs_change) > 20:  # Only notable changes
            merchant_changes.append((merchant, abs_change, pct_change, curr_total, prev_total))

    # Sort by absolute change and take top 5
    merchant_changes.sort(key=lambda x: abs(x[1]), reverse=True)
    for merchant, abs_change, pct_change, curr, prev in merchant_changes[:5]:
        if prev == 0:
            what = f"New merchant: {merchant} (${curr:.2f})"
            why = f"First time spending at {merchant} {period_label}"
            confidence = "medium"
        else:
            direction = "increased" if abs_change > 0 else "decreased"
            what = f"{merchant} spending {direction}: ${curr:.2f} vs ${prev:.2f}"
            why = f"Spending at {merchant} {direction} by ${abs(abs_change):.2f}"
            confidence = "high" if abs(pct_change) > 30 else "medium"

        insights.append(SpendingInsight(
            what_changed=what, why=why, confidence=confidence,
            category="merchant", amount_change=abs_change,
            percentage_change=pct_change,
            details={"merchant": merchant}
        ))

    # Sort by confidence (high first), then absolute change
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    insights.sort(key=lambda i: (confidence_order.get(i.confidence, 3), -abs(i.amount_change)))

    return insights


def get_spending_summary(transactions: list[dict]) -> dict:
    """Generate a summary of spending for a period."""
    if not transactions:
        return {"total": 0, "count": 0, "categories": {}, "top_merchants": []}

    total = sum(float(tx.get("amount", 0)) for tx in transactions)
    cats = _group_by_category(transactions)
    merchants = _group_by_merchant(transactions)

    top_merchants = sorted(
        [(m, sum(amts)) for m, amts in merchants.items()],
        key=lambda x: x[1], reverse=True
    )[:5]

    return {
        "total": round(total, 2),
        "count": len(transactions),
        "average": round(total / len(transactions), 2) if transactions else 0,
        "categories": {cat: round(sum(amts), 2) for cat, amts in cats.items()},
        "top_merchants": [(m, round(a, 2)) for m, a in top_merchants],
    }
