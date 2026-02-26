"""Transaction deduplication intelligence for imports and syncs."""

from difflib import SequenceMatcher
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from .extensions import db
from .models import Expense

bp = Blueprint("deduplication", __name__)

EXACT_MATCH_THRESHOLD = 0.85
AMOUNT_DATE_WEIGHT = 0.6
NOTES_WEIGHT = 0.4


def _notes_similarity(a: str | None, b: str | None) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def find_duplicates(user_id: int) -> list[dict]:
    """Find potential duplicate expense groups for a user."""
    expenses = (
        Expense.query.filter_by(user_id=user_id)
        .order_by(Expense.spent_at.desc())
        .all()
    )

    groups = []
    seen = set()

    for i, exp_a in enumerate(expenses):
        if exp_a.id in seen:
            continue
        group_members = []

        for j in range(i + 1, len(expenses)):
            exp_b = expenses[j]
            if exp_b.id in seen:
                continue

            # Same amount and date = high base confidence
            amount_match = float(exp_a.amount) == float(exp_b.amount)
            date_match = exp_a.spent_at == exp_b.spent_at
            category_match = exp_a.category_id == exp_b.category_id

            if not (amount_match and date_match):
                continue

            # Calculate confidence score
            base_score = AMOUNT_DATE_WEIGHT if (amount_match and date_match) else 0.0
            notes_score = _notes_similarity(exp_a.notes, exp_b.notes) * NOTES_WEIGHT
            confidence = base_score + notes_score

            # Boost for same category
            if category_match:
                confidence = min(confidence + 0.05, 1.0)

            if confidence >= EXACT_MATCH_THRESHOLD:
                group_members.append(
                    {"expense_id": exp_b.id, "confidence": round(confidence, 3)}
                )
                seen.add(exp_b.id)

        if group_members:
            seen.add(exp_a.id)
            groups.append(
                {
                    "anchor_id": exp_a.id,
                    "members": group_members,
                    "count": len(group_members) + 1,
                }
            )

    return groups


def merge_duplicate_group(user_id: int, keep_id: int, remove_ids: list[int]) -> int:
    """Merge a duplicate group by keeping one and deleting the rest."""
    keep = Expense.query.filter_by(id=keep_id, user_id=user_id).first()
    if not keep:
        return 0

    deleted = 0
    for rid in remove_ids:
        exp = Expense.query.filter_by(id=rid, user_id=user_id).first()
        if exp and exp.id != keep_id:
            db.session.delete(exp)
            deleted += 1

    db.session.commit()
    return deleted


@bp.get("/")
@jwt_required()
def get_duplicates():
    """Find potential duplicate transactions."""
    user_id = get_jwt_identity()
    groups = find_duplicates(user_id)
    return jsonify(duplicates=groups, total_groups=len(groups)), 200


@bp.post("/merge")
@jwt_required()
def merge_duplicates():
    """Merge a duplicate group, keeping one transaction."""
    user_id = get_jwt_identity()
    data = request.get_json() or {}

    keep_id = data.get("keep_id")
    remove_ids = data.get("remove_ids", [])

    if not keep_id or not remove_ids:
        return jsonify(error="keep_id and remove_ids are required"), 400

    if not isinstance(remove_ids, list):
        return jsonify(error="remove_ids must be a list"), 400

    deleted = merge_duplicate_group(user_id, keep_id, remove_ids)
    return jsonify(merged=deleted, kept=keep_id), 200
