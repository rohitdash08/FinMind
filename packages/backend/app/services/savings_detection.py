"""Savings opportunity detection engine.

Analyzes spending patterns to identify potential savings opportunities
including duplicate subscriptions, price increases, cheaper alternatives,
and unused services.
"""

from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from collections import defaultdict


class OpportunityType:
    DUPLICATE_SUB = "duplicate_subscription"
    PRICE_INCREASE = "price_increase"
    UNUSED_SUB = "unused_subscription"
    HIGH_FREQUENCY = "high_frequency_spending"
    CATEGORY_SPIKE = "category_spike"
    ROUND_UP = "round_up_savings"
    NEGOTIABLE = "negotiable_bill"


# Categories where bills are often negotiable
NEGOTIABLE_CATEGORIES = [
    "insurance", "internet", "phone", "cable", "utilities",
    "gym", "subscription", "streaming",
]

# Common duplicate subscription patterns
SUBSCRIPTION_GROUPS = {
    "streaming": ["netflix", "hulu", "disney", "hbo", "prime video", "apple tv", "paramount"],
    "music": ["spotify", "apple music", "youtube music", "tidal", "amazon music"],
    "cloud": ["icloud", "google one", "dropbox", "onedrive"],
    "news": ["nyt", "wsj", "washington post", "medium", "substack"],
    "fitness": ["gym", "peloton", "fitbit", "strava", "myfitnesspal"],
}


def detect_opportunities(
    expenses: List[dict],
    bills: Optional[List[dict]] = None,
    lookback_days: int = 90,
) -> dict:
    """Detect savings opportunities from spending data.

    Args:
        expenses: List of expense dicts with amount, category_name, notes, spent_at.
        bills: Optional list of bill dicts with name, amount, cadence.
        lookback_days: Days of history to analyze.

    Returns:
        Dict with opportunities, total potential savings, and summary.
    """
    opportunities = []
    cutoff = date.today() - timedelta(days=lookback_days)

    recent = [e for e in expenses if _parse_date(e.get("spent_at")) and _parse_date(e.get("spent_at")) >= cutoff]

    opportunities.extend(_detect_duplicates(recent, bills or []))
    opportunities.extend(_detect_price_increases(recent))
    opportunities.extend(_detect_high_frequency(recent))
    opportunities.extend(_detect_category_spikes(recent, lookback_days))
    opportunities.extend(_detect_negotiable(bills or []))
    round_up = _calculate_round_up(recent)

    total_savings = sum(o.get("potential_savings", 0) for o in opportunities)

    return {
        "opportunities": sorted(opportunities, key=lambda x: x.get("potential_savings", 0), reverse=True),
        "total_potential_monthly_savings": round(total_savings, 2),
        "round_up_savings_monthly": round(round_up, 2),
        "opportunity_count": len(opportunities),
        "analyzed_transactions": len(recent),
        "lookback_days": lookback_days,
    }


def _detect_duplicates(expenses: List[dict], bills: List[dict]) -> List[dict]:
    """Find duplicate subscriptions in the same category."""
    opportunities = []
    found_services = defaultdict(list)

    all_items = []
    for e in expenses:
        name = (e.get("notes") or e.get("category_name") or "").lower()
        all_items.append({"name": name, "amount": float(e.get("amount", 0))})
    for b in bills:
        name = (b.get("name") or "").lower()
        all_items.append({"name": name, "amount": float(b.get("amount", 0))})

    for group_name, keywords in SUBSCRIPTION_GROUPS.items():
        matches = []
        for item in all_items:
            for kw in keywords:
                if kw in item["name"]:
                    matches.append(item)
                    break
        if len(matches) > 1:
            cheapest = min(m["amount"] for m in matches)
            savings = sum(m["amount"] for m in matches) - cheapest
            opportunities.append({
                "type": OpportunityType.DUPLICATE_SUB,
                "title": f"Multiple {group_name} subscriptions detected",
                "description": f"Found {len(matches)} {group_name} services. Consider keeping only one.",
                "potential_savings": round(savings, 2),
                "priority": "high" if savings > 20 else "medium",
            })

    return opportunities


def _detect_price_increases(expenses: List[dict]) -> List[dict]:
    """Detect recurring charges that increased in price."""
    opportunities = []
    by_name = defaultdict(list)

    for e in expenses:
        name = (e.get("notes") or e.get("category_name") or "").lower().strip()
        if name:
            by_name[name].append({
                "amount": float(e.get("amount", 0)),
                "date": _parse_date(e.get("spent_at")),
            })

    for name, charges in by_name.items():
        if len(charges) < 2:
            continue
        sorted_charges = sorted(charges, key=lambda x: x["date"] if x["date"] else date.min)
        first = sorted_charges[0]["amount"]
        last = sorted_charges[-1]["amount"]
        if last > first and first > 0:
            increase_pct = (last - first) / first * 100
            if increase_pct >= 10:
                opportunities.append({
                    "type": OpportunityType.PRICE_INCREASE,
                    "title": f"Price increase detected: {name}",
                    "description": f"Increased {increase_pct:.0f}% from ${first:.2f} to ${last:.2f}",
                    "potential_savings": round(last - first, 2),
                    "priority": "medium",
                })

    return opportunities


def _detect_high_frequency(expenses: List[dict]) -> List[dict]:
    """Detect categories with unusually high transaction frequency."""
    opportunities = []
    by_category = defaultdict(list)

    for e in expenses:
        cat = e.get("category_name", "uncategorized")
        by_category[cat].append(float(e.get("amount", 0)))

    for cat, amounts in by_category.items():
        if len(amounts) >= 15:  # More than ~5x/month over 3 months
            total = sum(amounts)
            avg = total / len(amounts)
            opportunities.append({
                "type": OpportunityType.HIGH_FREQUENCY,
                "title": f"High frequency spending: {cat}",
                "description": f"{len(amounts)} transactions, avg ${avg:.2f} each, total ${total:.2f}",
                "potential_savings": round(total * 0.2, 2),  # Assume 20% reducible
                "priority": "medium",
            })

    return opportunities


def _detect_category_spikes(expenses: List[dict], lookback_days: int) -> List[dict]:
    """Detect categories where recent spending spiked vs historical average."""
    opportunities = []
    mid = date.today() - timedelta(days=lookback_days // 2)

    older = defaultdict(float)
    newer = defaultdict(float)
    older_days = 0
    newer_days = 0

    for e in expenses:
        d = _parse_date(e.get("spent_at"))
        cat = e.get("category_name", "uncategorized")
        amount = float(e.get("amount", 0))
        if d and d < mid:
            older[cat] += amount
        elif d:
            newer[cat] += amount

    for cat in newer:
        if cat in older and older[cat] > 0:
            increase = (newer[cat] - older[cat]) / older[cat] * 100
            if increase > 50 and newer[cat] - older[cat] > 20:
                opportunities.append({
                    "type": OpportunityType.CATEGORY_SPIKE,
                    "title": f"Spending spike: {cat}",
                    "description": f"Up {increase:.0f}% vs previous period (${older[cat]:.0f} → ${newer[cat]:.0f})",
                    "potential_savings": round((newer[cat] - older[cat]) * 0.5, 2),
                    "priority": "high" if increase > 100 else "medium",
                })

    return opportunities


def _detect_negotiable(bills: List[dict]) -> List[dict]:
    """Identify bills that are commonly negotiable."""
    opportunities = []
    for bill in bills:
        name = (bill.get("name") or "").lower()
        amount = float(bill.get("amount", 0))
        for keyword in NEGOTIABLE_CATEGORIES:
            if keyword in name and amount > 10:
                opportunities.append({
                    "type": OpportunityType.NEGOTIABLE,
                    "title": f"Negotiable bill: {bill.get('name')}",
                    "description": f"${amount:.2f}/period. Many providers offer discounts if you call and ask.",
                    "potential_savings": round(amount * 0.15, 2),
                    "priority": "low",
                })
                break
    return opportunities


def _calculate_round_up(expenses: List[dict]) -> float:
    """Calculate potential savings from round-up-to-dollar strategy."""
    total_round_up = 0
    for e in expenses:
        amount = float(e.get("amount", 0))
        cents = amount - int(amount)
        if cents > 0:
            total_round_up += 1 - cents

    if not expenses:
        return 0
    days = 90
    return round(total_round_up / days * 30, 2)


def _parse_date(val) -> Optional[date]:
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return date.fromisoformat(val[:10])
        except (ValueError, TypeError):
            return None
    return None
