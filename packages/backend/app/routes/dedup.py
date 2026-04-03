"""Transaction deduplication routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.deduplication import find_duplicates, merge_duplicates

bp = Blueprint("dedup", __name__)


@bp.get("")
@jwt_required()
def list_duplicates():
    """Find potential duplicate transactions.

    Query: lookback_days (default 90), min_confidence (default 50).
    """
    uid = int(get_jwt_identity())
    try:
        lookback = min(365, max(7, int(request.args.get("lookback_days", "90"))))
    except (ValueError, TypeError):
        lookback = 90
    try:
        min_conf = max(0, min(100, int(request.args.get("min_confidence", "50"))))
    except (ValueError, TypeError):
        min_conf = 50

    dupes = find_duplicates(uid, lookback_days=lookback)
    dupes = [d for d in dupes if d["confidence"] >= min_conf]
    return jsonify(dupes)


@bp.post("/merge")
@jwt_required()
def merge():
    """Merge a duplicate pair. Body: {keep_id, remove_id}."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    keep_id = data.get("keep_id")
    remove_id = data.get("remove_id")
    if not keep_id or not remove_id:
        return jsonify(error="keep_id and remove_id required"), 400
    if merge_duplicates(uid, keep_id, remove_id):
        return jsonify(message="merged")
    return jsonify(error="not found or unauthorized"), 404
