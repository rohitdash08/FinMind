from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.transaction_dedup import detect_duplicates

bp = Blueprint("transaction_dedup", __name__)


@bp.route("/deduplication", methods=["GET"])
@jwt_required()
def deduplication():
    """
    GET /insights/deduplication?months=3&days_window=2&min_confidence=0.7

    Detects potential duplicate transactions using multiple strategies:
    - Exact duplicates: same amount, date, category, type
    - Near-date duplicates: same amount within N days (configurable window)

    Returns duplicate groups with confidence scores, suggested keep/remove IDs.
    """
    user_id = get_jwt_identity()

    try:
        months = int(request.args.get("months", 3))
    except (ValueError, TypeError):
        months = 3
    try:
        days_window = int(request.args.get("days_window", 2))
    except (ValueError, TypeError):
        days_window = 2
    try:
        min_confidence = float(request.args.get("min_confidence", 0.7))
    except (ValueError, TypeError):
        min_confidence = 0.7

    result = detect_duplicates(
        user_id=int(user_id),
        months=months,
        days_window=days_window,
        min_confidence=min_confidence,
    )

    return jsonify(
        {
            "total_duplicates_found": result.total_duplicates_found,
            "estimated_duplicate_amount": result.estimated_duplicate_amount,
            "summary": result.summary,
            "duplicate_groups": [
                {
                    "transaction_ids": g.transaction_ids,
                    "confidence": g.confidence,
                    "reason": g.reason,
                    "suggested_keep_id": g.suggested_keep_id,
                    "amounts": g.amounts,
                    "dates": g.dates,
                    "descriptions": g.descriptions,
                }
                for g in result.duplicate_groups
            ],
        }
    )