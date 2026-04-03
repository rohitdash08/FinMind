"""
Subscription auto-detection service.

Scans the user's expense history and identifies recurring charges that match
subscription patterns (keyword match + monthly/weekly cadence detection).
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.models import db, Expense

# Keywords that strongly suggest a subscription service
_SUBSCRIPTION_KEYWORDS = [
    "netflix", "spotify", "hulu", "disney+", "disney plus", "amazon prime",
    "apple music", "apple tv", "icloud", "dropbox", "adobe",
    "microsoft 365", "office 365", "slack", "zoom", "notion",
    "github", "heroku", "aws", "gcp", "azure", "digitalocean",
    "linode", "cloudflare", "vpn", "antivirus", "grammarly",
    "chatgpt", "openai", "claude", "subscription", "monthly", "annual",
    "yearly", "plan", "premium", "pro plan", "basic plan",
]

# Tolerance window (days) for considering charges as "monthly"
_MONTHLY_TOLERANCE = 7
_WEEKLY_TOLERANCE = 2


def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _is_keyword_match(note: str) -> bool:
    n = _normalize(note)
    return any(kw in n for kw in _SUBSCRIPTION_KEYWORDS)


def _detect_cadence(sorted_dates: list[date]) -> str | None:
    """
    Given a sorted list of expense dates, determine if they follow a
    weekly or monthly cadence within the allowed tolerance.
    Returns 'weekly', 'monthly', or None.
    """
    if len(sorted_dates) < 2:
        return None

    gaps = [(sorted_dates[i + 1] - sorted_dates[i]).days for i in range(len(sorted_dates) - 1)]
    avg_gap = sum(gaps) / len(gaps)

    if all(abs(g - 7) <= _WEEKLY_TOLERANCE for g in gaps):
        return "weekly"
    if all(abs(g - 30) <= _MONTHLY_TOLERANCE for g in gaps):
        return "monthly"
    # Looser check for monthly if avg is close and most gaps are in range
    monthly_count = sum(1 for g in gaps if abs(g - 30) <= _MONTHLY_TOLERANCE)
    if monthly_count >= len(gaps) * 0.7 and 20 <= avg_gap <= 40:
        return "monthly"
    return None


def detect_subscriptions(uid: int, months: int = 6) -> dict[str, Any]:
    """
    Auto-detect subscriptions from recurring charges in the user's expense history.

    Strategy:
    1. Group expenses by normalized note/merchant (case-insensitive).
    2. Retain groups with >= 2 occurrences.
    3. For each group, check for keyword match OR recurring cadence (weekly/monthly).
    4. Compute estimated monthly cost and confidence score.

    Returns a dict with:
      - subscriptions: list of detected subscription objects
      - total_monthly_estimate: sum of estimated monthly costs (Decimal)
      - analysis_period_months: the requested look-back period
    """
    months = max(1, min(months, 24))
    cutoff = date.today() - timedelta(days=30 * months)

    expenses = (
        db.session.query(Expense)
        .filter(
            Expense.user_id == uid,
            Expense.expense_type == "EXPENSE",
            Expense.spent_at >= cutoff,
        )
        .order_by(Expense.spent_at)
        .all()
    )

    # Group by normalized notes
    groups: dict[str, list[Expense]] = defaultdict(list)
    for exp in expenses:
        note = _normalize(exp.notes or "")
        if note:
            groups[note].append(exp)

    subscriptions = []
    for note, exps in groups.items():
        if len(exps) < 2:
            continue

        sorted_dates = sorted(e.spent_at for e in exps)
        cadence = _detect_cadence(sorted_dates)
        kw_match = _is_keyword_match(note)

        if cadence is None and not kw_match:
            continue

        amounts = [Decimal(str(e.amount)) for e in exps]
        avg_amount = sum(amounts) / len(amounts)

        # Estimate monthly cost
        if cadence == "weekly":
            monthly_estimate = avg_amount * Decimal("4.33")
        else:
            monthly_estimate = avg_amount

        # Confidence: higher if both keyword match + cadence detected
        if cadence and kw_match:
            confidence = "high"
        elif cadence:
            confidence = "medium"
        else:
            confidence = "low"

        subscriptions.append(
            {
                "merchant": note,
                "cadence": cadence or "irregular",
                "occurrences": len(exps),
                "average_amount": float(round(avg_amount, 2)),
                "currency": exps[0].currency,
                "monthly_estimate": float(round(monthly_estimate, 2)),
                "confidence": confidence,
                "keyword_match": kw_match,
                "last_charge": sorted_dates[-1].isoformat(),
                "first_charge": sorted_dates[0].isoformat(),
            }
        )

    # Sort by monthly estimate descending
    subscriptions.sort(key=lambda s: s["monthly_estimate"], reverse=True)

    total_monthly = sum(Decimal(str(s["monthly_estimate"])) for s in subscriptions)

    return {
        "subscriptions": subscriptions,
        "total_monthly_estimate": float(round(total_monthly, 2)),
        "analysis_period_months": months,
    }