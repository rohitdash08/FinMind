"""Transaction deduplication intelligence.

Detects and manages duplicate transactions using fingerprint-based
matching with configurable similarity thresholds.
"""

import hashlib
import json
import logging
import re
from datetime import datetime, date, timedelta
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import func, and_

from ..extensions import db
from ..models import Expense, DuplicateGroup

logger = logging.getLogger("finmind.dedup")


def compute_fingerprint(
    amount: Decimal | float,
    currency: str,
    spent_at: date,
    notes: str | None = None,
    category_id: int | None = None,
) -> str:
    """Compute a fingerprint for an expense.

    The fingerprint is a SHA-256 hash of normalized transaction attributes.
    Same-day transactions with matching amount, currency, and similar notes
    produce the same fingerprint.
    """
    normalized_notes = _normalize_text(notes) if notes else ""
    parts = [
        f"amt:{float(amount):.2f}",
        f"cur:{currency.upper()}",
        f"date:{spent_at.isoformat()}",
        f"notes:{normalized_notes}",
    ]
    if category_id:
        parts.append(f"cat:{category_id}")

    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_fuzzy_fingerprint(
    amount: Decimal | float,
    currency: str,
    spent_at: date,
) -> str:
    """Compute a fuzzy fingerprint (amount + currency + date only).

    Used for detecting potential duplicates where notes may differ
    but the core financial attributes match.
    """
    parts = [
        f"amt:{float(amount):.2f}",
        f"cur:{currency.upper()}",
        f"date:{spent_at.isoformat()}",
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def scan_duplicates(
    user_id: int,
    date_window: int = 1,
    amount_tolerance: float = 0.0,
) -> dict:
    """Scan all expenses for potential duplicates.

    Args:
        user_id: User ID to scan.
        date_window: Days window to consider for fuzzy matching (0 = exact).
        amount_tolerance: Amount tolerance for fuzzy matching (0 = exact).

    Returns:
        Summary with duplicate groups found.
    """
    expenses = (
        Expense.query
        .filter_by(user_id=user_id)
        .order_by(Expense.spent_at.desc())
        .all()
    )

    # Compute fingerprints and update expenses
    for exp in expenses:
        fp = compute_fingerprint(
            exp.amount, exp.currency, exp.spent_at,
            exp.notes, exp.category_id,
        )
        exp.fingerprint = fp

    db.session.commit()

    # Find exact duplicates (same fingerprint)
    exact_groups = _find_exact_duplicates(expenses)

    # Find fuzzy duplicates (similar amount + date within window)
    fuzzy_groups = _find_fuzzy_duplicates(
        expenses, date_window, amount_tolerance
    )

    # Create duplicate groups
    new_groups = 0
    for fp, expense_ids in {**exact_groups, **fuzzy_groups}.items():
        if len(expense_ids) < 2:
            continue

        existing = DuplicateGroup.query.filter_by(
            user_id=user_id, fingerprint=fp
        ).first()

        if not existing:
            group = DuplicateGroup(
                user_id=user_id,
                fingerprint=fp,
                expense_ids=json.dumps(expense_ids),
                status="PENDING",
            )
            db.session.add(group)
            new_groups += 1
        else:
            # Update expense_ids if group already exists
            existing.expense_ids = json.dumps(expense_ids)

    db.session.commit()

    total_dupes = sum(
        len(ids) for ids in {**exact_groups, **fuzzy_groups}.items()
        if len(ids) >= 2
    )

    logger.info(
        "Scan user=%d: %d groups, %d potential duplicates",
        user_id, new_groups, total_dupes,
    )

    return {
        "scanned": len(expenses),
        "duplicate_groups": new_groups + len(
            DuplicateGroup.query.filter_by(user_id=user_id).all()
        ) - new_groups,
        "new_groups": new_groups,
        "potential_duplicates": total_dupes,
    }


def get_duplicate_groups(
    user_id: int,
    status: str | None = None,
) -> list[dict]:
    """Get all duplicate groups for a user.

    Args:
        user_id: User ID.
        status: Optional status filter (PENDING, RESOLVED, IGNORED).
    """
    query = DuplicateGroup.query.filter_by(user_id=user_id)
    if status:
        query = query.filter_by(status=status.upper())

    groups = query.order_by(DuplicateGroup.created_at.desc()).all()
    result = []

    for group in groups:
        # Find matching expenses using stored IDs
        matching = _get_group_expenses(user_id, group)

        result.append({
            "id": group.id,
            "fingerprint": group.fingerprint,
            "status": group.status,
            "master_expense_id": group.master_expense_id,
            "created_at": group.created_at.isoformat() if group.created_at else None,
            "resolved_at": group.resolved_at.isoformat() if group.resolved_at else None,
            "expenses": [_expense_to_dict(e) for e in matching],
            "count": len(matching),
        })

    return result


def resolve_duplicate_group(
    user_id: int,
    group_id: int,
    action: str,
    keep_expense_id: int | None = None,
) -> dict | None:
    """Resolve a duplicate group.

    Args:
        user_id: User ID.
        group_id: Duplicate group ID.
        action: Resolution action (keep_one, keep_all, merge, ignore).
        keep_expense_id: ID of expense to keep (for keep_one action).

    Returns:
        Updated group or None if not found.
    """
    group = DuplicateGroup.query.filter_by(
        id=group_id, user_id=user_id
    ).first()
    if not group:
        return None

    matching = _get_group_expenses(user_id, group)

    deleted_count = 0

    if action == "keep_one" and keep_expense_id:
        # Keep specified expense, delete others
        for exp in matching:
            if exp.id != keep_expense_id:
                db.session.delete(exp)
                deleted_count += 1
        group.master_expense_id = keep_expense_id
        group.status = "RESOLVED"
        group.resolved_at = datetime.utcnow()

    elif action == "keep_all":
        # Mark all as not duplicates
        group.status = "RESOLVED"
        group.resolved_at = datetime.utcnow()

    elif action == "merge":
        # Keep the oldest, sum amounts if different, delete rest
        if matching:
            oldest = min(matching, key=lambda e: e.created_at or datetime.min)
            for exp in matching:
                if exp.id != oldest.id:
                    db.session.delete(exp)
                    deleted_count += 1
            group.master_expense_id = oldest.id
            group.status = "RESOLVED"
            group.resolved_at = datetime.utcnow()

    elif action == "ignore":
        group.status = "IGNORED"
        group.resolved_at = datetime.utcnow()

    else:
        return None

    db.session.commit()
    logger.info(
        "Resolved group=%d action=%s deleted=%d user=%d",
        group_id, action, deleted_count, user_id,
    )

    return {
        "id": group.id,
        "status": group.status,
        "action": action,
        "deleted_count": deleted_count,
        "resolved_at": group.resolved_at.isoformat() if group.resolved_at else None,
    }


def get_dedup_stats(user_id: int) -> dict:
    """Get deduplication statistics for a user."""
    total_expenses = Expense.query.filter_by(user_id=user_id).count()
    fingerprinted = (
        Expense.query
        .filter(
            Expense.user_id == user_id,
            Expense.fingerprint.isnot(None),
        )
        .count()
    )

    pending = DuplicateGroup.query.filter_by(
        user_id=user_id, status="PENDING"
    ).count()
    resolved = DuplicateGroup.query.filter_by(
        user_id=user_id, status="RESOLVED"
    ).count()
    ignored = DuplicateGroup.query.filter_by(
        user_id=user_id, status="IGNORED"
    ).count()

    return {
        "total_expenses": total_expenses,
        "fingerprinted": fingerprinted,
        "coverage": round(fingerprinted / total_expenses * 100, 1) if total_expenses > 0 else 0,
        "groups": {
            "pending": pending,
            "resolved": resolved,
            "ignored": ignored,
            "total": pending + resolved + ignored,
        },
    }


# ─── Internal helpers ────────────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Remove common suffixes/prefixes that don't affect identity
    text = re.sub(r"\b(ref|reference|txn|transaction|#)\s*:?\s*\S+", "", text)
    return text.strip()


def _find_exact_duplicates(expenses: list) -> dict[str, list[int]]:
    """Group expenses by exact fingerprint match."""
    groups: dict[str, list[int]] = defaultdict(list)
    for exp in expenses:
        if exp.fingerprint:
            groups[exp.fingerprint].append(exp.id)
    return {fp: ids for fp, ids in groups.items() if len(ids) >= 2}


def _find_fuzzy_duplicates(
    expenses: list, date_window: int, amount_tolerance: float,
) -> dict[str, list[int]]:
    """Find fuzzy duplicates within date and amount tolerance."""
    if date_window == 0 and amount_tolerance == 0:
        return {}

    groups: dict[str, list[int]] = defaultdict(list)
    for exp in expenses:
        fuzzy_fp = compute_fuzzy_fingerprint(
            exp.amount, exp.currency, exp.spent_at,
        )
        groups[f"fuzzy_{fuzzy_fp}"].append(exp.id)

    # If date_window > 0, also check nearby dates
    if date_window > 0:
        by_amount = defaultdict(list)
        for exp in expenses:
            key = f"{float(exp.amount):.2f}_{exp.currency}"
            by_amount[key].append(exp)

        for key, exps in by_amount.items():
            if len(exps) < 2:
                continue
            exps.sort(key=lambda e: e.spent_at)
            for i in range(len(exps)):
                for j in range(i + 1, len(exps)):
                    diff = abs((exps[j].spent_at - exps[i].spent_at).days)
                    if diff <= date_window:
                        fuzzy_key = f"window_{key}_{exps[i].spent_at.isoformat()}"
                        if exps[i].id not in groups.get(fuzzy_key, []):
                            groups[fuzzy_key].append(exps[i].id)
                        if exps[j].id not in groups.get(fuzzy_key, []):
                            groups[fuzzy_key].append(exps[j].id)

    return {fp: ids for fp, ids in groups.items() if len(ids) >= 2}


def _fuzzy_match_for_group(user_id: int, fingerprint: str) -> list:
    """Find expenses that could match a group fingerprint."""
    return []


def _get_group_expenses(user_id: int, group: DuplicateGroup) -> list:
    """Get expenses belonging to a duplicate group.

    Uses stored expense_ids first, falls back to fingerprint matching.
    """
    if group.expense_ids:
        try:
            ids = json.loads(group.expense_ids)
            expenses = Expense.query.filter(
                Expense.id.in_(ids),
                Expense.user_id == user_id,
            ).all()
            if expenses:
                return expenses
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback to fingerprint matching
    return Expense.query.filter_by(
        user_id=user_id, fingerprint=group.fingerprint
    ).all()


def _expense_to_dict(exp: Expense) -> dict:
    return {
        "id": exp.id,
        "amount": float(exp.amount),
        "currency": exp.currency,
        "notes": exp.notes,
        "spent_at": exp.spent_at.isoformat() if exp.spent_at else None,
        "expense_type": exp.expense_type,
        "category_id": exp.category_id,
        "fingerprint": exp.fingerprint,
        "created_at": exp.created_at.isoformat() if exp.created_at else None,
    }
