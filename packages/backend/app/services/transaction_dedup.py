from __future__ import annotations

import hashlib
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, and_, or_

from app.models import Transaction
from app import db


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DuplicateGroup:
    transaction_ids: list[int]
    confidence: float            # 0.0 - 1.0
    reason: str                  # why these are considered duplicates
    suggested_keep_id: int       # which one to keep (oldest)
    amounts: list[float]
    dates: list[str]
    descriptions: list[str]


@dataclass
class DeduplicationResult:
    duplicate_groups: list[DuplicateGroup]
    total_duplicates_found: int
    estimated_duplicate_amount: float  # total amount of duplicate transactions
    summary: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_description(desc: Optional[str]) -> str:
    """Normalize a transaction description for comparison."""
    if not desc:
        return ""
    # Lowercase, strip numbers that vary (reference IDs, etc.)
    import re
    normalized = desc.lower().strip()
    normalized = re.sub(r'\d+', 'N', normalized)  # replace all numbers
    normalized = re.sub(r'\s+', ' ', normalized)   # collapse whitespace
    return normalized


def _date_str(tx_date) -> str:
    if isinstance(tx_date, date):
        return tx_date.isoformat()
    return str(tx_date)


# ---------------------------------------------------------------------------
# Detection strategies
# ---------------------------------------------------------------------------

def _find_exact_duplicates(transactions: list) -> list[DuplicateGroup]:
    """Find transactions with identical amount + date + category."""
    groups: dict[str, list] = {}
    for tx in transactions:
        key = f"{tx.amount}_{_date_str(tx.date)}_{tx.category or ''}_{tx.type}"
        if key not in groups:
            groups[key] = []
        groups[key].append(tx)

    result = []
    for key, txs in groups.items():
        if len(txs) >= 2:
            sorted_txs = sorted(txs, key=lambda t: t.id)
            result.append(
                DuplicateGroup(
                    transaction_ids=[t.id for t in sorted_txs],
                    confidence=0.99,
                    reason="Exact match: same amount, date, category, and type.",
                    suggested_keep_id=sorted_txs[0].id,
                    amounts=[float(t.amount) for t in sorted_txs],
                    dates=[_date_str(t.date) for t in sorted_txs],
                    descriptions=[t.description or "" for t in sorted_txs],
                )
            )
    return result


def _find_near_date_duplicates(transactions: list, days_window: int = 2) -> list[DuplicateGroup]:
    """Find transactions with same amount within N days of each other."""
    # Group by amount + type + category
    by_key: dict[str, list] = {}
    for tx in transactions:
        key = f"{float(tx.amount):.2f}_{tx.type}_{tx.category or ''}"
        if key not in by_key:
            by_key[key] = []
        by_key[key].append(tx)

    result = []
    seen_pairs: set = set()

    for key, txs in by_key.items():
        if len(txs) < 2:
            continue
        # Sort by date
        try:
            sorted_txs = sorted(txs, key=lambda t: (str(t.date), t.id))
        except Exception:
            sorted_txs = txs

        for i in range(len(sorted_txs)):
            for j in range(i + 1, len(sorted_txs)):
                tx_a = sorted_txs[i]
                tx_b = sorted_txs[j]

                pair_key = tuple(sorted([tx_a.id, tx_b.id]))
                if pair_key in seen_pairs:
                    continue

                # Date proximity check
                try:
                    date_a = date.fromisoformat(str(tx_a.date)) if not isinstance(tx_a.date, date) else tx_a.date
                    date_b = date.fromisoformat(str(tx_b.date)) if not isinstance(tx_b.date, date) else tx_b.date
                    delta = abs((date_a - date_b).days)
                except (ValueError, AttributeError):
                    delta = 999

                if delta <= days_window and delta > 0:  # > 0 excludes exact date (caught above)
                    seen_pairs.add(pair_key)
                    pair_sorted = sorted([tx_a, tx_b], key=lambda t: t.id)
                    result.append(
                        DuplicateGroup(
                            transaction_ids=[t.id for t in pair_sorted],
                            confidence=0.75,
                            reason=f"Same amount ${float(tx_a.amount):.2f} within {delta} day(s). Possible import duplicate.",
                            suggested_keep_id=pair_sorted[0].id,
                            amounts=[float(t.amount) for t in pair_sorted],
                            dates=[_date_str(t.date) for t in pair_sorted],
                            descriptions=[t.description or "" for t in pair_sorted],
                        )
                    )

    return result


# ---------------------------------------------------------------------------
# Main service
# ---------------------------------------------------------------------------

def detect_duplicates(
    user_id: int,
    months: int = 3,
    days_window: int = 2,
    min_confidence: float = 0.7,
) -> DeduplicationResult:
    """
    Detect duplicate transactions using multiple strategies.

    Args:
        user_id: JWT user id
        months: how many months back to scan (1-12)
        days_window: near-date window in days (0-7)
        min_confidence: minimum confidence threshold for results
    """
    months = max(1, min(12, months))
    days_window = max(0, min(7, days_window))

    cutoff = date.today() - timedelta(days=months * 31)

    transactions = (
        db.session.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.date >= cutoff,
        )
        .all()
    )

    if not transactions:
        return DeduplicationResult(
            duplicate_groups=[],
            total_duplicates_found=0,
            estimated_duplicate_amount=0.0,
            summary="No transactions found in the selected period.",
        )

    all_groups: list[DuplicateGroup] = []

    # Strategy 1: Exact duplicates (highest confidence)
    exact = _find_exact_duplicates(transactions)
    all_groups.extend(exact)

    # Strategy 2: Near-date duplicates (only if window > 0)
    if days_window > 0:
        # Exclude transaction IDs already in exact groups
        exact_ids = {tid for g in exact for tid in g.transaction_ids}
        non_exact = [t for t in transactions if t.id not in exact_ids]
        near = _find_near_date_duplicates(non_exact, days_window=days_window)
        all_groups.extend(near)

    # Filter by min_confidence
    all_groups = [g for g in all_groups if g.confidence >= min_confidence]

    # Sort by confidence desc
    all_groups.sort(key=lambda g: -g.confidence)

    total_duplicates = sum(len(g.transaction_ids) - 1 for g in all_groups)  # extras to remove
    estimated_amount = sum(
        g.amounts[0] * (len(g.transaction_ids) - 1)  # duplicate amounts
        for g in all_groups
    )
    estimated_amount = round(estimated_amount, 2)

    if not all_groups:
        summary = "No duplicate transactions detected in the selected period."
    else:
        summary = (
            f"Found {len(all_groups)} duplicate group(s) with {total_duplicates} "
            f"extra transaction(s) totaling ${estimated_amount:.2f}."
        )

    return DeduplicationResult(
        duplicate_groups=all_groups,
        total_duplicates_found=total_duplicates,
        estimated_duplicate_amount=estimated_amount,
        summary=summary,
    )