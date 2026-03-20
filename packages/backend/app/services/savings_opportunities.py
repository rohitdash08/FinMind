"""
Savings Opportunity Detection Engine — FinMind (#119)

Analyzes user spending patterns to identify concrete areas where
the user can reduce expenses. Returns ranked, actionable insights.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import TypedDict

from sqlalchemy import func, extract

from ..extensions import db
from ..models import Category, Expense

logger = logging.getLogger("finmind.savings_opportunities")

# ── Tuneable thresholds ────────────────────────────────────────────────────────
OVERSPEND_RATIO = Decimal("1.20")   # 20 % above 3-month average → flag
HIGH_FREQ_DAILY = 3                 # 3+ same-category transactions/day
SMALL_TICKET_MAX = Decimal("200")   # "small ticket" threshold (INR / default currency)
MIN_MONTHS_HISTORY = 2              # need at least 2 prior months to compare


class SavingsOpportunity(TypedDict):
    id: str
    title: str
    description: str
    category: str | None
    estimated_savings: float
    priority: str   # "high" | "medium" | "low"
    rule: str


# ── Internal helpers ───────────────────────────────────────────────────────────

def _current_period(ym: str) -> tuple[date, date]:
    """Return (first_day, last_day) for a YYYY-MM string."""
    year, month = int(ym[:4]), int(ym[5:7])
    first = date(year, month, 1)
    if month == 12:
        last = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def _prior_months(ym: str, n: int) -> list[str]:
    """Return the n month strings preceding ym (most-recent first)."""
    year, month = int(ym[:4]), int(ym[5:7])
    result: list[str] = []
    for _ in range(n):
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def _category_spend_month(uid: int, ym: str) -> dict[int, dict]:
    """Aggregated spend per category for a given month.

    Returns { category_id: { "name": str, "total": Decimal, "count": int } }
    """
    year, month = int(ym[:4]), int(ym[5:7])
    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            func.sum(Expense.amount).label("total"),
            func.count(Expense.id).label("cnt"),
        )
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
        )
        .group_by(Expense.category_id, Category.name)
        .all()
    )
    return {
        row.category_id: {
            "name": row.name or "Uncategorized",
            "total": row.total or Decimal("0"),
            "count": row.cnt or 0,
        }
        for row in rows
    }


def _avg_category_spend(uid: int, months: list[str]) -> dict[int, Decimal]:
    """Average spend per category across a list of months."""
    if not months:
        return {}

    totals: dict[int, Decimal] = {}
    counts: dict[int, int] = {}

    for ym in months:
        monthly = _category_spend_month(uid, ym)
        for cat_id, data in monthly.items():
            totals[cat_id] = totals.get(cat_id, Decimal("0")) + data["total"]
            counts[cat_id] = counts.get(cat_id, 0) + 1

    return {
        cat_id: totals[cat_id] / Decimal(str(counts[cat_id]))
        for cat_id in totals
    }


def _daily_frequency(uid: int, first: date, last: date) -> dict[int, dict]:
    """Days with 3+ same-category transactions in a date range."""
    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            Expense.spent_at,
            func.count(Expense.id).label("cnt"),
        )
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= first,
            Expense.spent_at <= last,
        )
        .group_by(Expense.category_id, Category.name, Expense.spent_at)
        .having(func.count(Expense.id) >= HIGH_FREQ_DAILY)
        .all()
    )
    result: dict[int, dict] = {}
    for row in rows:
        if row.category_id not in result:
            result[row.category_id] = {
                "name": row.name or "Uncategorized",
                "days": 0,
            }
        result[row.category_id]["days"] += 1
    return result


def _small_ticket_drain(uid: int, first: date, last: date) -> dict[int, dict]:
    """Categories where most transactions are small-ticket but total is significant."""
    rows = (
        db.session.query(
            Expense.category_id,
            Category.name,
            func.count(Expense.id).label("cnt"),
            func.sum(Expense.amount).label("total"),
            func.avg(Expense.amount).label("avg_amt"),
        )
        .outerjoin(Category, Category.id == Expense.category_id)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= first,
            Expense.spent_at <= last,
            Expense.amount <= SMALL_TICKET_MAX,
        )
        .group_by(Expense.category_id, Category.name)
        .having(func.count(Expense.id) >= 5)
        .all()
    )
    return {
        row.category_id: {
            "name": row.name or "Uncategorized",
            "count": row.cnt,
            "total": row.total or Decimal("0"),
            "avg": row.avg_amt or Decimal("0"),
        }
        for row in rows
    }


# ── Detection rules ────────────────────────────────────────────────────────────

def _rule_category_overspend(
    uid: int, ym: str, current: dict[int, dict], avg: dict[int, Decimal]
) -> list[SavingsOpportunity]:
    opportunities: list[SavingsOpportunity] = []
    for cat_id, data in current.items():
        baseline = avg.get(cat_id)
        if baseline is None or baseline == 0:
            continue
        if data["total"] > baseline * OVERSPEND_RATIO:
            excess = float(data["total"] - baseline)
            opportunities.append(
                SavingsOpportunity(
                    id=f"overspend-{cat_id}",
                    title=f"High spending in {data[name]}",
                    description=(
                        f"You spent {float(data[total]):.2f} this month in "
                        f"{data[name]}, which is "
                        f"{((data[total] / baseline) - 1) * 100:.0f}% above "
                        f"your {MIN_MONTHS_HISTORY}-month average of "
                        f"{float(baseline):.2f}. "
                        f"Cutting back to your average could save you ~{excess:.2f}."
                    ),
                    category=data["name"],
                    estimated_savings=round(excess, 2),
                    priority="high" if excess > float(baseline) * 0.5 else "medium",
                    rule="category_overspend",
                )
            )
    return opportunities


def _rule_high_frequency(
    uid: int, first: date, last: date, high_freq: dict[int, dict]
) -> list[SavingsOpportunity]:
    opportunities: list[SavingsOpportunity] = []
    for cat_id, data in high_freq.items():
        opportunities.append(
            SavingsOpportunity(
                id=f"highfreq-{cat_id}",
                title=f"Frequent transactions in {data[name]}",
                description=(
                    f"You made {HIGH_FREQ_DAILY}+ separate transactions per day in "
                    f"{data[name]} on {data[days]} day(s) this month. "
                    f"Consolidating purchases can reduce impulse spending."
                ),
                category=data["name"],
                estimated_savings=0.0,
                priority="medium",
                rule="high_frequency",
            )
        )
    return opportunities


def _rule_small_ticket_drain(
    uid: int, small_tickets: dict[int, dict]
) -> list[SavingsOpportunity]:
    opportunities: list[SavingsOpportunity] = []
    for cat_id, data in small_tickets.items():
        opportunities.append(
            SavingsOpportunity(
                id=f"smallticket-{cat_id}",
                title=f"Small purchases adding up in {data[name]}",
                description=(
                    f"You made {data[count]} small purchases (avg "
                    f"{float(data[avg]):.2f} each) in {data[name]} "
                    f"totalling {float(data[total]):.2f} this month. "
                    f"Consider setting a weekly budget for this category."
                ),
                category=data["name"],
                estimated_savings=round(float(data["total"]) * 0.2, 2),
                priority="low",
                rule="small_ticket_drain",
            )
        )
    return opportunities


def _rule_no_savings_category(
    uid: int, current: dict[int, dict], savings_keywords: tuple[str, ...]
) -> list[SavingsOpportunity]:
    """Warn if no income/savings-type transactions exist this month."""
    savings_keywords = ("saving", "investment", "fd", "rd", "ppf", "nps", "elss")
    has_savings = any(
        any(kw in (data["name"] or "").lower() for kw in savings_keywords)
        for data in current.values()
    )
    if not has_savings:
        return [
            SavingsOpportunity(
                id="no-savings",
                title="No savings or investment transactions detected",
                description=(
                    "We did not detect any transactions in savings or investment "
                    "categories this month. Try setting aside even 5-10% of your "
                    "income to build an emergency fund."
                ),
                category=None,
                estimated_savings=0.0,
                priority="high",
                rule="no_savings_category",
            )
        ]
    return []


# ── Public API ─────────────────────────────────────────────────────────────────

def detect_savings_opportunities(uid: int, ym: str) -> dict:
    """
    Analyse spending for user ``uid`` in month ``ym`` (YYYY-MM) and return
    a dict with a list of ranked SavingsOpportunity items plus summary stats.
    """
    first, last = _current_period(ym)
    prior_yms = _prior_months(ym, MIN_MONTHS_HISTORY)

    current = _category_spend_month(uid, ym)
    avg = _avg_category_spend(uid, prior_yms)
    high_freq = _daily_frequency(uid, first, last)
    small_tickets = _small_ticket_drain(uid, first, last)

    opportunities: list[SavingsOpportunity] = []
    opportunities.extend(_rule_category_overspend(uid, ym, current, avg))
    opportunities.extend(_rule_high_frequency(uid, first, last, high_freq))
    opportunities.extend(_rule_small_ticket_drain(uid, small_tickets))
    opportunities.extend(
        _rule_no_savings_category(uid, current, savings_keywords=())
    )

    # Sort: high first, then by estimated_savings desc
    priority_order = {"high": 0, "medium": 1, "low": 2}
    opportunities.sort(
        key=lambda o: (priority_order.get(o["priority"], 3), -o["estimated_savings"])
    )

    total_potential = sum(o["estimated_savings"] for o in opportunities)
    total_spent = float(sum(d["total"] for d in current.values()))

    logger.info(
        "Savings opportunities: user=%s month=%s found=%d potential=%.2f",
        uid, ym, len(opportunities), total_potential,
    )

    return {
        "month": ym,
        "total_spent": round(total_spent, 2),
        "total_potential_savings": round(total_potential, 2),
        "opportunities_count": len(opportunities),
        "opportunities": list(opportunities),
    }
