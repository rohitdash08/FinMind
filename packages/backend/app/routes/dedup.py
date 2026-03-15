"""Transaction deduplication routes.

Provides endpoints for scanning, reviewing, and resolving
duplicate transactions.
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.dedup import (
    scan_duplicates,
    get_duplicate_groups,
    resolve_duplicate_group,
    get_dedup_stats,
)

bp = Blueprint("dedup", __name__)


@bp.route("/scan", methods=["POST"])
@jwt_required()
def scan():
    """Scan expenses for potential duplicates.

    Body (optional):
        date_window: Days window for fuzzy matching (default: 1)
        amount_tolerance: Amount tolerance for fuzzy matching (default: 0)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    date_window = data.get("date_window", 1)
    amount_tolerance = data.get("amount_tolerance", 0.0)

    if date_window < 0 or date_window > 30:
        return jsonify({"error": "date_window must be between 0 and 30"}), 400
    if amount_tolerance < 0:
        return jsonify({"error": "amount_tolerance must be >= 0"}), 400

    result = scan_duplicates(user_id, date_window, amount_tolerance)
    return jsonify(result), 200


@bp.route("/groups", methods=["GET"])
@jwt_required()
def list_groups():
    """List duplicate groups.

    Query Parameters:
        status: Filter by status (PENDING, RESOLVED, IGNORED)
    """
    user_id = int(get_jwt_identity())
    status = request.args.get("status", None)
    groups = get_duplicate_groups(user_id, status)
    return jsonify({"groups": groups, "count": len(groups)}), 200


@bp.route("/groups/<int:group_id>/resolve", methods=["POST"])
@jwt_required()
def resolve(group_id: int):
    """Resolve a duplicate group.

    Body:
        action: keep_one, keep_all, merge, or ignore
        keep_expense_id: ID of expense to keep (required for keep_one)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    action = data.get("action", "").lower()

    valid_actions = {"keep_one", "keep_all", "merge", "ignore"}
    if action not in valid_actions:
        return jsonify({
            "error": f"Invalid action. Use: {', '.join(sorted(valid_actions))}"
        }), 400

    keep_id = data.get("keep_expense_id")
    if action == "keep_one" and not keep_id:
        return jsonify({"error": "keep_expense_id required for keep_one action"}), 400

    result = resolve_duplicate_group(user_id, group_id, action, keep_id)
    if result is None:
        return jsonify({"error": "Duplicate group not found"}), 404

    return jsonify(result), 200


@bp.route("/stats", methods=["GET"])
@jwt_required()
def stats():
    """Get deduplication statistics."""
    user_id = int(get_jwt_identity())
    result = get_dedup_stats(user_id)
    return jsonify(result), 200
