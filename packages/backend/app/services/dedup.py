import logging
from datetime import date, timedelta
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Any

from flask import current_app
from sqlalchemy import and_, or_

from ..extensions import db
from ..models import Expense, User

logger = logging.getLogger("finmind.dedup")

FUZZY_SIMILARITY_THRESHOLD = 0.85
AMOUNT_OFFSET_TOLERANCE = Decimal("0.50")


def score_similarity(a: dict[str, Any], b: dict[str, Any]) -> float:
    desc_a = str(a.get("description", "")).strip().lower()
    desc_b = str(b.get("description", "")).strip().lower()
    desc_score = SequenceMatcher(None, desc_a, desc_b).ratio()

    amt_a = _to_decimal(a.get("amount"))
    amt_b = _to_decimal(b.get("amount"))
    amount_score = 1.0 if amt_a is not None and amt_b is not None and amt_a == amt_b else 0.0
    if amount_score == 0.0 and amt_a is not None and amt_b is not None:
        diff = abs(amt_a - amt_b)
        if diff <= AMOUNT_OFFSET_TOLERANCE:
            amount_score = 0.9
        elif diff <= Decimal("5.00"):
            amount_score = 0.6

    date_a = a.get("date") or a.get("spent_at")
    date_b = b.get("date") or b.get("spent_at")
    date_score = 0.0
    if date_a and date_b:
        try:
            da = date.fromisoformat(str(date_a)[:10]) if isinstance(date_a, str) else date_a
            db_ = date.fromisoformat(str(date_b)[:10]) if isinstance(date_b, str) else date_b
            if isinstance(da, date) and isinstance(db_, date):
                diff_days = abs((da - db_).days)
                if diff_days == 0:
                    date_score = 1.0
                elif diff_days <= 3:
                    date_score = 0.8
                elif diff_days <= 7:
                    date_score = 0.5
        except (ValueError, TypeError):
            pass

    combined = desc_score * 0.5 + amount_score * 0.3 + date_score * 0.2
    return round(combined, 4)


def find_duplicates(
    user_id: int,
    transactions: list[dict[str, Any]],
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    existing = (
        db.session.query(Expense)
        .filter_by(user_id=user_id)
        .order_by(Expense.spent_at.desc())
        .limit(5000)
        .all()
    )
    if not existing:
        return []

    results: list[dict[str, Any]] = []
    for tx in transactions:
        tx_desc = str(tx.get("description", "")).strip().lower()
        tx_amt = _to_decimal(tx.get("amount"))
        tx_date_str = tx.get("date") or tx.get("spent_at")
        if not tx_desc or tx_amt is None or not tx_date_str:
            continue
        matches = []
        for exp in existing:
            exp_desc = (exp.notes or "").strip().lower()
            if not exp_desc:
                continue
            desc_score = SequenceMatcher(None, tx_desc, exp_desc).ratio()
            amt_diff = abs(tx_amt - exp.amount) if exp.amount else Decimal("9999")
            amt_match = 1.0 if amt_diff == 0 else (0.9 if amt_diff <= AMOUNT_OFFSET_TOLERANCE else (0.6 if amt_diff <= Decimal("5.00") else 0.0))
            day_diff = abs((exp.spent_at - date.fromisoformat(str(tx_date_str)[:10])).days) if isinstance(tx_date_str, str) else 999
            date_match = 1.0 if day_diff == 0 else (0.8 if day_diff <= 3 else (0.5 if day_diff <= 7 else 0.0))
            combined = desc_score * 0.5 + amt_match * 0.3 + date_match * 0.2
            if combined >= threshold:
                matches.append({
                    "existing_id": exp.id,
                    "existing_description": exp.notes,
                    "existing_amount": float(exp.amount),
                    "existing_date": exp.spent_at.isoformat(),
                    "score": round(combined, 4),
                })
        if matches:
            matches.sort(key=lambda m: m["score"], reverse=True)
            results.append({
                "candidate": tx,
                "matches": matches[:5],
                "best_score": matches[0]["score"],
                "resolved": matches[0]["score"] >= 0.95,
            })
    return results


def find_potential_duplicate(
    user_id: int,
    row: dict[str, Any],
    threshold: float = 0.7,
) -> dict[str, Any] | None:
    results = find_duplicates(user_id, [row], threshold)
    return results[0] if results else None


def resolve_ambiguous(
    user_id: int,
    candidates: list[dict[str, Any]],
    resolutions: list[dict[str, Any]],
) -> dict[str, Any]:
    skipped = 0
    marked_resolved = 0
    for res in resolutions:
        candidate_id = res.get("candidate_id")
        action = res.get("action")
        existing_id = res.get("existing_id")

        if action == "skip":
            skipped += 1
        elif action == "merge" and existing_id:
            expense = db.session.get(Expense, existing_id)
            if expense and expense.user_id == user_id:
                if res.get("update_amount"):
                    expense.amount = _to_decimal(res["update_amount"]) or expense.amount
                if res.get("update_description"):
                    expense.notes = res["update_description"][:500]
                db.session.commit()
                marked_resolved += 1
        elif action == "keep_both":
            skipped += 1
    return {
        "skipped": skipped,
        "marked_resolved": marked_resolved,
    }


def _to_decimal(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"))
    except (ValueError, TypeError, ArithmeticError):
        return None
