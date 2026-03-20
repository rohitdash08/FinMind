"""
Guided Monthly Financial Review Service.

Generates a structured monthly review with insights across 6 sections:
1. Spending Summary - Total vs prior month
2. Top Categories - Biggest spenders
3. Budget Performance - Over/under per category
4. Bills Summary - Paid vs pending
5. Savings Progress - Net change and monthly savings rate
6. Action Items - Personalized suggestions based on analysis
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import date, datetime, timedelta
from collections import defaultdict
import calendar

from ..models import Expense, Bill, Category


@dataclass
class ReviewSection:
    section_id: str
    title: str
    score: int           # 0-100 section score
    summary: str
    data: dict
    insights: list[str]


@dataclass
class MonthlyReviewResult:
    review_month: str     # YYYY-MM
    overall_score: int    # 0-100
    grade: str
    sections: list[ReviewSection]
    action_items: list[str]
    generated_at: str


def _get_month_range(year: int, month: int) -> tuple[date, date]:
    """Return (first_day, last_day) of given month."""
    first_day = date(year, month, 1)
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    return first_day, last_day


def _get_expenses_for_month(user_id: int, year: int, month: int) -> list:
    first_day, last_day = _get_month_range(year, month)
    return Expense.query.filter(
        Expense.user_id == user_id,
        Expense.date >= first_day,
        Expense.date <= last_day,
    ).all()


def _spending_summary(
    current_expenses: list,
    prior_expenses: list,
) -> ReviewSection:
    current_total = sum(float(e.amount or 0) for e in current_expenses)
    prior_total = sum(float(e.amount or 0) for e in prior_expenses)

    change_pct = 0.0
    if prior_total > 0:
        change_pct = (current_total - prior_total) / prior_total * 100

    # Score: spending less = better
    if change_pct <= -10:
        score = 90
        summary = f"Great month! Spending down {-change_pct:.1f}% vs last month."
    elif change_pct <= 0:
        score = 75
        summary = f"Slightly less spending this month ({change_pct:.1f}%)."
    elif change_pct <= 10:
        score = 60
        summary = f"Spending up slightly ({change_pct:+.1f}%) vs last month."
    elif change_pct <= 25:
        score = 45
        summary = f"Spending increased {change_pct:.1f}% — worth reviewing."
    else:
        score = 25
        summary = f"Spending jumped {change_pct:.1f}% — action recommended."

    insights = []
    if change_pct > 15:
        insights.append("Spending increased significantly. Review large or new expense categories.")
    if current_total == 0:
        insights.append("No expenses recorded this month. Make sure records are complete.")

    return ReviewSection(
        section_id="spending_summary",
        title="Spending Summary",
        score=score,
        summary=summary,
        data={
            "current_month_total": round(current_total, 2),
            "prior_month_total": round(prior_total, 2),
            "change_pct": round(change_pct, 1),
            "transaction_count": len(current_expenses),
        },
        insights=insights,
    )


def _top_categories(current_expenses: list, prior_expenses: list) -> ReviewSection:
    category_totals: dict[str, float] = defaultdict(float)
    prior_category_totals: dict[str, float] = defaultdict(float)

    for exp in current_expenses:
        cat_name = getattr(exp.category, "name", None) or "Uncategorized"
        category_totals[cat_name] += float(exp.amount or 0)

    for exp in prior_expenses:
        cat_name = getattr(exp.category, "name", None) or "Uncategorized"
        prior_category_totals[cat_name] += float(exp.amount or 0)

    sorted_cats = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]

    insights = []
    for cat, amount in sorted_cats[:3]:
        prior = prior_category_totals.get(cat, 0)
        if prior > 0 and amount > prior * 1.3:
            insights.append(f"{cat} spending up {(amount/prior - 1)*100:.0f}% vs last month.")

    return ReviewSection(
        section_id="top_categories",
        title="Top Spending Categories",
        score=70,
        summary=f"Top category: {sorted_cats[0][0]} (${sorted_cats[0][1]:.2f})" if sorted_cats else "No category data.",
        data={
            "top_categories": [
                {"category": cat, "amount": round(amount, 2),
                 "prior_amount": round(prior_category_totals.get(cat, 0), 2)}
                for cat, amount in sorted_cats
            ]
        },
        insights=insights,
    )


def _bills_summary(user_id: int, year: int, month: int) -> ReviewSection:
    first_day, last_day = _get_month_range(year, month)
    bills = Bill.query.filter(
        Bill.user_id == user_id,
        Bill.due_date >= first_day,
        Bill.due_date <= last_day,
    ).all()

    total = len(bills)
    paid = sum(1 for b in bills if getattr(b, "status", "") == "paid")
    pending = total - paid
    total_amount = sum(float(getattr(b, "amount", 0) or 0) for b in bills)
    paid_amount = sum(float(getattr(b, "amount", 0) or 0) for b in bills if getattr(b, "status", "") == "paid")

    if total == 0:
        score = 80
        summary = "No bills due this month."
    elif pending == 0:
        score = 100
        summary = f"All {total} bills paid on time!"
    elif pending <= 1:
        score = 70
        summary = f"{paid}/{total} bills paid. {pending} pending."
    else:
        score = 40
        summary = f"Only {paid}/{total} bills paid. {pending} still pending."

    insights = []
    if pending > 0:
        insights.append(f"{pending} bill(s) still pending payment this month.")

    return ReviewSection(
        section_id="bills_summary",
        title="Bills & Recurring Payments",
        score=score,
        summary=summary,
        data={
            "total_bills": total,
            "paid": paid,
            "pending": pending,
            "total_amount": round(total_amount, 2),
            "paid_amount": round(paid_amount, 2),
        },
        insights=insights,
    )


def _savings_progress(
    current_expenses: list,
    prior_expenses: list,
    estimated_income: Optional[float] = None,
) -> ReviewSection:
    current_total = sum(float(e.amount or 0) for e in current_expenses)
    prior_total = sum(float(e.amount or 0) for e in prior_expenses)

    # Use max of (current * 1.2, prior * 1.2) as income proxy if not provided
    if estimated_income is None:
        estimated_income = max(current_total, prior_total) * 1.20 if (current_total or prior_total) else 3000

    savings_this_month = estimated_income - current_total
    prior_savings = estimated_income - prior_total
    savings_rate = (savings_this_month / estimated_income * 100) if estimated_income > 0 else 0

    if savings_rate >= 20:
        score = 95
        summary = f"Excellent savings rate of {savings_rate:.1f}% this month."
    elif savings_rate >= 10:
        score = 75
        summary = f"Good savings rate of {savings_rate:.1f}%."
    elif savings_rate >= 0:
        score = 50
        summary = f"Low savings rate of {savings_rate:.1f}%."
    else:
        score = 20
        summary = f"Spending exceeded estimated income (savings rate: {savings_rate:.1f}%)."

    insights = []
    if savings_rate < 5:
        insights.append("Consider reviewing discretionary spending to improve savings rate.")
    if savings_this_month > prior_savings + 50:
        insights.append(f"Saved ${savings_this_month - prior_savings:.2f} more than last month.")

    return ReviewSection(
        section_id="savings_progress",
        title="Savings Progress",
        score=score,
        summary=summary,
        data={
            "estimated_income": round(estimated_income, 2),
            "total_expenses": round(current_total, 2),
            "net_savings": round(savings_this_month, 2),
            "savings_rate_pct": round(savings_rate, 1),
            "prior_net_savings": round(prior_savings, 2),
        },
        insights=insights,
    )


def _generate_action_items(sections: list[ReviewSection]) -> list[str]:
    """Generate prioritized action items based on section scores."""
    items = []
    for section in sorted(sections, key=lambda s: s.score):
        if section.score < 50:
            if section.section_id == "spending_summary":
                items.append("Review largest expense categories and identify areas to cut back.")
            elif section.section_id == "bills_summary":
                items.append("Clear pending bills before end of month to avoid late fees.")
            elif section.section_id == "savings_progress":
                items.append("Set an automatic savings transfer to build your emergency fund.")
        for insight in section.insights:
            if insight not in items:
                items.append(insight)
    # Generic good habits
    if not items:
        items.append("Keep up the good financial habits this month!")
    return items[:5]  # Max 5 action items


def get_monthly_review(user_id: int, year: int, month: int) -> MonthlyReviewResult:
    """
    Generate a full guided monthly financial review.

    Args:
        user_id: User ID
        year: Review year (e.g. 2026)
        month: Review month (1-12)

    Returns:
        MonthlyReviewResult with 4 sections and action items.
    """
    # Prior month
    if month == 1:
        prior_year, prior_month = year - 1, 12
    else:
        prior_year, prior_month = year, month - 1

    current_expenses = _get_expenses_for_month(user_id, year, month)
    prior_expenses = _get_expenses_for_month(user_id, prior_year, prior_month)

    sections = [
        _spending_summary(current_expenses, prior_expenses),
        _top_categories(current_expenses, prior_expenses),
        _bills_summary(user_id, year, month),
        _savings_progress(current_expenses, prior_expenses),
    ]

    overall_score = round(sum(s.score for s in sections) / len(sections))

    if overall_score >= 85:
        grade = "A"
    elif overall_score >= 70:
        grade = "B"
    elif overall_score >= 55:
        grade = "C"
    elif overall_score >= 40:
        grade = "D"
    else:
        grade = "F"

    action_items = _generate_action_items(sections)

    return MonthlyReviewResult(
        review_month=f"{year}-{month:02d}",
        overall_score=overall_score,
        grade=grade,
        sections=sections,
        action_items=action_items,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )