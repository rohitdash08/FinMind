"""Comparative Spending Analysis for FinMind.

Compare spending across:
- Categories (category A vs category B)
- Time periods (this month vs last month)
- Merchants (merchant A vs merchant B)
- Income vs expenses
"""

import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

from ..extensions import db

logger = logging.getLogger("finmind.comparative")


def compare_categories(transactions: list[dict]) -> dict:
    """Compare spending across all categories.

    Returns ranked categories with totals, averages, transaction counts.
    Includes pairwise comparisons for top categories.
    """
    cat_data = defaultdict(lambda: {"amounts": [], "count": 0, "total": 0.0})

    for tx in transactions:
        cat = tx.get("category", "uncategorized")
        amount = float(tx.get("amount", 0))
        cat_data[cat]["amounts"].append(amount)
        cat_data[cat]["count"] += 1
        cat_data[cat]["total"] += amount

    categories = []
    for cat, data in cat_data.items():
        avg = data["total"] / data["count"] if data["count"] else 0
        min_amt = min(data["amounts"]) if data["amounts"] else 0
        max_amt = max(data["amounts"]) if data["amounts"] else 0

        categories.append({
            "category": cat,
            "total_spent": round(data["total"], 2),
            "transaction_count": data["count"],
            "average_amount": round(avg, 2),
            "min_amount": round(min_amt, 2),
            "max_amount": round(max_amt, 2),
        })

    categories.sort(key=lambda x: x["total_spent"], reverse=True)

    # Pairwise comparisons for top 5
    top5 = categories[:5]
    comparisons = []
    for i in range(len(top5)):
        for j in range(i + 1, len(top5)):
            a, b = top5[i], top5[j]
            diff = a["total_spent"] - b["total_spent"]
            pct = (diff / b["total_spent"] * 100) if b["total_spent"] else 0
            comparisons.append({
                "category_a": a["category"],
                "category_b": b["category"],
                "difference": round(diff, 2),
                "percentage_difference": round(pct, 1),
                "winner": a["category"] if diff > 0 else b["category"],
            })

    return {
        "categories": categories,
        "pairwise_comparisons": comparisons[:10],
        "total_categories": len(categories),
    }


def compare_periods(
    current_transactions: list[dict],
    previous_transactions: list[dict],
    current_label: str = "current period",
    previous_label: str = "previous period",
) -> dict:
    """Compare spending between two time periods.

    Analyzes:
    - Total spending change
    - Category-level changes
    - New/removed categories
    - Merchant changes
    """
    def summarize(txs):
        total = sum(float(t.get("amount", 0)) for t in txs)
        cats = defaultdict(float)
        merchants = defaultdict(float)
        for t in txs:
            cats[t.get("category", "uncategorized")] += float(t.get("amount", 0))
            merchants[t.get("merchant", "Unknown")] += float(t.get("amount", 0))
        return total, dict(cats), dict(merchants)

    curr_total, curr_cats, curr_merchants = summarize(current_transactions)
    prev_total, prev_cats, prev_merchants = summarize(previous_transactions)

    # Total change
    total_diff = curr_total - prev_total
    total_pct = (total_diff / prev_total * 100) if prev_total else 0

    # Category changes
    all_cats = set(list(curr_cats.keys()) + list(prev_cats.keys()))
    category_changes = []
    for cat in all_cats:
        curr = curr_cats.get(cat, 0)
        prev = prev_cats.get(cat, 0)
        diff = curr - prev
        pct = (diff / prev * 100) if prev else (100 if curr > 0 else 0)
        status = "new" if prev == 0 and curr > 0 else "removed" if curr == 0 else "changed"

        category_changes.append({
            "category": cat,
            f"{current_label}": round(curr, 2),
            f"{previous_label}": round(prev, 2),
            "difference": round(diff, 2),
            "percentage_change": round(pct, 1),
            "status": status,
        })

    category_changes.sort(key=lambda x: abs(x["difference"]), reverse=True)

    # Top merchant changes
    all_merchants = set(list(curr_merchants.keys()) + list(prev_merchants.keys()))
    merchant_changes = []
    for m in all_merchants:
        curr = curr_merchants.get(m, 0)
        prev = prev_merchants.get(m, 0)
        if abs(curr - prev) > 5:  # Only significant changes
            merchant_changes.append({
                "merchant": m,
                "current": round(curr, 2),
                "previous": round(prev, 2),
                "difference": round(curr - prev, 2),
            })
    merchant_changes.sort(key=lambda x: abs(x["difference"]), reverse=True)

    return {
        "total": {
            "current": round(curr_total, 2),
            "previous": round(prev_total, 2),
            "difference": round(total_diff, 2),
            "percentage_change": round(total_pct, 1),
        },
        "category_changes": category_changes,
        "merchant_changes": merchant_changes[:10],
        "summary": {
            "categories_increased": len([c for c in category_changes if c["difference"] > 0]),
            "categories_decreased": len([c for c in category_changes if c["difference"] < 0]),
            "new_categories": len([c for c in category_changes if c["status"] == "new"]),
            "removed_categories": len([c for c in category_changes if c["status"] == "removed"]),
        },
    }


def compare_income_expenses(
    income: float,
    transactions: list[dict],
) -> dict:
    """Compare income vs expenses and provide savings analysis."""
    total_expenses = sum(float(t.get("amount", 0)) for t in transactions)
    savings = income - total_expenses
    savings_rate = (savings / income * 100) if income else 0
    expense_ratio = (total_expenses / income * 100) if income else 0

    # Category breakdown of expenses
    cat_totals = defaultdict(float)
    for t in transactions:
        cat_totals[t.get("category", "uncategorized")] += float(t.get("amount", 0))

    top_expense = max(cat_totals.items(), key=lambda x: x[1]) if cat_totals else ("none", 0)

    # Assessment
    if savings_rate >= 20:
        assessment = "excellent"
    elif savings_rate >= 10:
        assessment = "good"
    elif savings_rate >= 0:
        assessment = "needs_improvement"
    else:
        assessment = "overspending"

    return {
        "income": round(income, 2),
        "total_expenses": round(total_expenses, 2),
        "savings": round(savings, 2),
        "savings_rate": round(savings_rate, 1),
        "expense_ratio": round(expense_ratio, 1),
        "assessment": assessment,
        "top_expense_category": {"name": top_expense[0], "amount": round(top_expense[1], 2)},
        "category_breakdown": {k: round(v, 2) for k, v in sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)},
    }
