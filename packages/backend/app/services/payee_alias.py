from __future__ import annotations

import re
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
class PayeeAlias:
    canonical_name: str          # clean, recognized payee name
    raw_variants: list[str]      # raw descriptions that map to this payee
    total_spend: float
    transaction_count: int
    category_hint: str
    last_seen: str               # YYYY-MM-DD


@dataclass
class PayeeAliasResult:
    aliases: list[PayeeAlias]
    total_payees_found: int
    summary: str


# ---------------------------------------------------------------------------
# Payee canonicalization rules
# ---------------------------------------------------------------------------

# Known merchant patterns: (regex pattern, canonical name, category)
MERCHANT_RULES = [
    (r'amazon|amzn', 'Amazon', 'shopping'),
    (r'starbucks|sbux', 'Starbucks', 'dining'),
    (r'uber\s*eats|ubereats', 'Uber Eats', 'dining'),
    (r'\buber\b', 'Uber', 'transport'),
    (r'lyft', 'Lyft', 'transport'),
    (r'netflix', 'Netflix', 'entertainment'),
    (r'spotify', 'Spotify', 'entertainment'),
    (r'apple|itunes|app store', 'Apple', 'shopping'),
    (r'google|play store', 'Google', 'shopping'),
    (r'walmart|wal.mart', 'Walmart', 'groceries'),
    (r'target', 'Target', 'shopping'),
    (r'costco', 'Costco', 'groceries'),
    (r'whole foods|wholefoods', 'Whole Foods', 'groceries'),
    (r'trader joe', 'Trader Joes', 'groceries'),
    (r'cvs|cvs pharmacy', 'CVS', 'healthcare'),
    (r'walgreen|walgreens', 'Walgreens', 'healthcare'),
    (r'shell|shell gas', 'Shell', 'transport'),
    (r'chevron', 'Chevron', 'transport'),
    (r'bp\s|british petroleum', 'BP', 'transport'),
    (r'mcdonald|mcd |mcds', 'McDonalds', 'dining'),
    (r'chipotle', 'Chipotle', 'dining'),
    (r'dominos|domino.s', "Domino's", 'dining'),
    (r'doordash', 'DoorDash', 'dining'),
    (r'instacart', 'Instacart', 'groceries'),
    (r'best buy|bestbuy', 'Best Buy', 'shopping'),
    (r'home depot', 'Home Depot', 'shopping'),
    (r'lowes|lowe.s', "Lowe's", 'shopping'),
    (r'gym|fitness|planet fitness|la fitness|anytime fitness', 'Gym', 'fitness'),
    (r'airbnb', 'Airbnb', 'travel'),
    (r'booking\.com', 'Booking.com', 'travel'),
    (r'expedia', 'Expedia', 'travel'),
    (r'paypal', 'PayPal', 'transfer'),
    (r'venmo', 'Venmo', 'transfer'),
    (r'zelle', 'Zelle', 'transfer'),
]


def _get_canonical(description: str) -> tuple[Optional[str], str]:
    """Return (canonical_name, category) or (None, 'other') if no match."""
    desc_lower = description.lower()
    for pattern, canonical, category in MERCHANT_RULES:
        if re.search(pattern, desc_lower):
            return canonical, category
    return None, 'other'


def _normalize_raw(description: str) -> str:
    """Normalize a raw description for grouping similar variants."""
    # Remove common noise
    normalized = re.sub(r'[*#\d]+', '', description)  # strip ref numbers
    normalized = re.sub(r'\s+', ' ', normalized).strip().lower()
    # Keep first 40 chars as key
    return normalized[:40]


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

def get_payee_aliases(
    user_id: int,
    months: int = 6,
    min_transactions: int = 2,
) -> PayeeAliasResult:
    """
    Identify and group payee aliases from transaction descriptions.

    Groups raw descriptions by canonical merchant name and returns
    a clean alias map with spend stats.

    Args:
        user_id: JWT user id
        months: how many months to analyze (1-24)
        min_transactions: minimum transactions to include a payee
    """
    months = max(1, min(24, months))
    cutoff = date.today() - timedelta(days=months * 31)

    rows = (
        db.session.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
            Transaction.type == "expense",
        )
        .all()
    )

    if not rows:
        return PayeeAliasResult(
            aliases=[],
            total_payees_found=0,
            summary="No transactions found in the selected period.",
        )

    # Group by canonical name
    groups: dict[str, dict] = {}

    for tx in rows:
        desc = tx.description or tx.category or "Unknown"
        canonical, category = _get_canonical(desc)

        if canonical is None:
            # Fallback: use normalized description as key
            canonical = _normalize_raw(desc).title()[:30] or "Other"

        if canonical not in groups:
            groups[canonical] = {
                "raw_variants": set(),
                "total_spend": 0.0,
                "count": 0,
                "category": category,
                "last_seen": None,
            }

        g = groups[canonical]
        g["raw_variants"].add(desc[:80])
        g["total_spend"] += float(tx.amount or 0)
        g["count"] += 1

        try:
            tx_date = tx.date if isinstance(tx.date, date) else date.fromisoformat(str(tx.date))
            tx_date_str = tx_date.isoformat()
        except (ValueError, AttributeError):
            tx_date_str = "unknown"

        if g["last_seen"] is None or tx_date_str > g["last_seen"]:
            g["last_seen"] = tx_date_str

    # Convert to dataclass list, filter by min_transactions
    aliases: list[PayeeAlias] = []
    for canonical, data in groups.items():
        if data["count"] < min_transactions:
            continue
        aliases.append(
            PayeeAlias(
                canonical_name=canonical,
                raw_variants=sorted(data["raw_variants"])[:10],  # cap variants shown
                total_spend=round(data["total_spend"], 2),
                transaction_count=data["count"],
                category_hint=data["category"],
                last_seen=data["last_seen"] or "unknown",
            )
        )

    # Sort by total spend descending
    aliases.sort(key=lambda a: -a.total_spend)

    summary = (
        f"Identified {len(aliases)} distinct payees from {len(rows)} transactions "
        f"over the past {months} months."
        if aliases
        else "No payees met the minimum transaction threshold."
    )

    return PayeeAliasResult(
        aliases=aliases,
        total_payees_found=len(aliases),
        summary=summary,
    )