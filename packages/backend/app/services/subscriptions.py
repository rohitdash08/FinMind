"""
Subscription intelligence services for FinMind.

Implements:
- Auto-detect subscriptions from recurring charges (#109)
- Subscription cost increase detection (#110)
- Transaction deduplication intelligence (#113)
- Lifestyle inflation detection insights (#118)
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func

from ..extensions import db
from ..models import Expense


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_merchant(notes: str) -> str:
    """Strip common noise words and lower-case a merchant description."""
    if not notes:
        return ""
    # Drop common suffixes like "payment", "charge", "recurring"
    cleaned = re.sub(
        r"\b(payment|charge|recurring|auto|autopay|debit|credit|online|txn|ref|inv)\b",
        "",
        notes.lower(),
        flags=re.IGNORECASE,
    )
    # Collapse whitespace
    return re.sub(r"\s+", " ", cleaned).strip()


def _expenses_for_user(uid: int, months: int = 12) -> list[Expense]:
    """Return the last N months of expenses for a user."""
    cutoff = date.today() - timedelta(days=30 * months)
    return (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.spent_at >= cutoff,
            Expense.expense_type != "INCOME",
        )
        .order_by(Expense.spent_at.asc())
        .all()
    )


# ---------------------------------------------------------------------------
# Subscription detection (#109)
# ---------------------------------------------------------------------------

def detect_subscriptions(uid: int) -> dict[str, Any]:
    """
    Detect likely subscription services from recurring charges.

    A group of expenses is considered a subscription candidate when:
    - The same normalised merchant name appears in ≥ 2 distinct calendar months.
    - The amounts are consistent (within 5 % of each other).
    - The mean inter-charge interval is 7, 14, 30, or 365 days (±30 %).

    Returns a dict with ``subscriptions`` list and summary stats.
    """
    expenses = _expenses_for_user(uid, months=13)

    # Group by normalised merchant name
    groups: dict[str, list[Expense]] = defaultdict(list)
    for exp in expenses:
        key = _normalize_merchant(exp.notes or "")
        if key:
            groups[key].append(exp)

    subscriptions = []
    for merchant, items in groups.items():
        if len(items) < 2:
            continue

        # Check amount consistency
        amounts = [float(i.amount) for i in items]
        mean_amount = sum(amounts) / len(amounts)
        if mean_amount == 0:
            continue
        max_deviation = max(abs(a - mean_amount) / mean_amount for a in amounts)
        if max_deviation > 0.05:
            continue

        # Check interval consistency
        dates = sorted(i.spent_at for i in items)
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        if not gaps:
            continue
        mean_gap = sum(gaps) / len(gaps)
        # Known cadences (days): weekly=7, biweekly=14, monthly~30, yearly~365
        for target in (7, 14, 30, 365):
            if abs(mean_gap - target) / target <= 0.30:
                cadence = {7: "weekly", 14: "biweekly", 30: "monthly", 365: "yearly"}[
                    target
                ]
                subscriptions.append(
                    {
                        "merchant": merchant,
                        "cadence": cadence,
                        "mean_amount": round(mean_amount, 2),
                        "occurrences": len(items),
                        "last_seen": max(i.spent_at for i in items).isoformat(),
                        "annual_cost_estimate": round(
                            mean_amount * (365 / target), 2
                        ),
                    }
                )
                break

    total_annual = sum(s["annual_cost_estimate"] for s in subscriptions)
    return {
        "subscriptions": subscriptions,
        "total_subscriptions_found": len(subscriptions),
        "estimated_annual_cost": round(total_annual, 2),
        "estimated_monthly_cost": round(total_annual / 12, 2),
    }


# ---------------------------------------------------------------------------
# Subscription cost increase detection (#110)
# ---------------------------------------------------------------------------

def detect_subscription_cost_increases(uid: int) -> dict[str, Any]:
    """
    Identify subscriptions where the charged amount has recently increased.

    Compares the most recent charge for each detected subscription against
    the median of prior charges, flagging any increase > 2 %.
    """
    sub_data = detect_subscriptions(uid)
    expenses = _expenses_for_user(uid, months=13)

    increases = []
    for sub in sub_data["subscriptions"]:
        merchant = sub["merchant"]
        items = sorted(
            [e for e in expenses if _normalize_merchant(e.notes or "") == merchant],
            key=lambda e: e.spent_at,
        )
        if len(items) < 2:
            continue

        latest_amount = float(items[-1].amount)
        prior_amounts = [float(i.amount) for i in items[:-1]]
        median_prior = sorted(prior_amounts)[len(prior_amounts) // 2]

        if median_prior == 0:
            continue
        change_pct = (latest_amount - median_prior) / median_prior * 100

        if change_pct > 2.0:
            increases.append(
                {
                    "merchant": merchant,
                    "previous_amount": round(median_prior, 2),
                    "current_amount": round(latest_amount, 2),
                    "increase_pct": round(change_pct, 2),
                    "detected_on": items[-1].spent_at.isoformat(),
                }
            )

    return {
        "cost_increases": increases,
        "total_increases_found": len(increases),
    }


# ---------------------------------------------------------------------------
# Transaction deduplication (#113)
# ---------------------------------------------------------------------------

def find_duplicate_transactions(uid: int) -> dict[str, Any]:
    """
    Identify likely duplicate expenses.

    Two expenses are considered duplicates when:
    - Same normalised merchant name.
    - Same amount (within 1 cent).
    - Within 3 days of each other.
    """
    expenses = _expenses_for_user(uid, months=6)
    duplicates = []
    seen_pairs: set[tuple[int, int]] = set()

    for i, a in enumerate(expenses):
        for b in expenses[i + 1 :]:
            if (a.id, b.id) in seen_pairs or (b.id, a.id) in seen_pairs:
                continue

            gap_days = abs((b.spent_at - a.spent_at).days)
            if gap_days > 3:
                continue

            amount_match = abs(float(a.amount) - float(b.amount)) < 0.01
            if not amount_match:
                continue

            merchant_a = _normalize_merchant(a.notes or "")
            merchant_b = _normalize_merchant(b.notes or "")
            if not merchant_a or merchant_a != merchant_b:
                continue

            seen_pairs.add((a.id, b.id))
            duplicates.append(
                {
                    "expense_id_1": a.id,
                    "expense_id_2": b.id,
                    "merchant": merchant_a,
                    "amount": float(a.amount),
                    "date_1": a.spent_at.isoformat(),
                    "date_2": b.spent_at.isoformat(),
                    "gap_days": gap_days,
                }
            )

    total_duplicate_amount = sum(d["amount"] for d in duplicates)
    return {
        "duplicates": duplicates,
        "total_duplicates_found": len(duplicates),
        "total_duplicate_amount": round(total_duplicate_amount, 2),
    }


# ---------------------------------------------------------------------------
# Lifestyle inflation detection (#118)
# ---------------------------------------------------------------------------

def detect_lifestyle_inflation(uid: int) -> dict[str, Any]:
    """
    Detect rising lifestyle expenses over time.

    Compares average monthly discretionary spend over the last 3 months
    against the 3 months before that, and breaks down categories that are
    growing faster than the overall average.
    """
    expenses = _expenses_for_user(uid, months=6)

    # Split into two 3-month windows: recent vs comparison
    cutoff = date.today() - timedelta(days=90)
    recent = [e for e in expenses if e.spent_at >= cutoff]
    older = [e for e in expenses if e.spent_at < cutoff]

    def _sum_by_category(items: list[Expense]) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for e in items:
            key = str(e.category_id or "uncat")
            totals[key] += float(e.amount)
        return dict(totals)

    recent_by_cat = _sum_by_category(recent)
    older_by_cat = _sum_by_category(older)

    all_cats = set(recent_by_cat) | set(older_by_cat)

    recent_total = sum(recent_by_cat.values())
    older_total = sum(older_by_cat.values())

    if older_total == 0:
        overall_change_pct = 0.0
    else:
        overall_change_pct = (recent_total - older_total) / older_total * 100

    category_changes = []
    for cat in all_cats:
        old_v = older_by_cat.get(cat, 0.0)
        new_v = recent_by_cat.get(cat, 0.0)
        if old_v == 0:
            continue
        pct = (new_v - old_v) / old_v * 100
        if pct > 5.0:  # only report meaningful increases
            category_changes.append(
                {
                    "category_id": cat,
                    "older_3m_total": round(old_v, 2),
                    "recent_3m_total": round(new_v, 2),
                    "change_pct": round(pct, 2),
                }
            )

    category_changes.sort(key=lambda x: x["change_pct"], reverse=True)

    return {
        "older_3m_total": round(older_total, 2),
        "recent_3m_total": round(recent_total, 2),
        "overall_change_pct": round(overall_change_pct, 2),
        "inflation_detected": overall_change_pct > 5.0,
        "growing_categories": category_changes,
    }
