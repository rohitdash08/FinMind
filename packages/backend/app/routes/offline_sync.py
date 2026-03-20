from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.offline_sync import process_sync_batch, ConflictStrategy

bp = Blueprint("offline_sync", __name__)


@bp.route("/sync", methods=["POST"])
@jwt_required()
def sync_batch():
    """
    POST /insights/sync
    Apply a batch of offline operations from the client.

    Body:
    {
        "conflict_strategy": "last_write_wins",
        "operations": [
            {
                "operation_id": "client-uuid-1",
                "operation_type": "create",
                "record_type": "expense",
                "record_id": null,
                "payload": { "description": "Coffee", "amount": 4.50, "date": "2026-03-20" },
                "client_timestamp": "2026-03-20T08:00:00Z",
                "client_version": 1
            }
        ]
    }

    Returns per-operation results with applied/conflicted/rejected counts.
    """
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    operations = body.get("operations", [])
    conflict_strategy = body.get("conflict_strategy", ConflictStrategy.LAST_WRITE_WINS)

    if not isinstance(operations, list):
        return jsonify({"error": "operations must be a list"}), 400
    if len(operations) > 500:
        return jsonify({"error": "Maximum 500 operations per batch"}), 400

    result = process_sync_batch(user_id, operations, conflict_strategy)
    return jsonify({
        "total": result.total,
        "applied": result.applied,
        "conflicted": result.conflicted,
        "rejected": result.rejected,
        "sync_token": result.sync_token,
        "server_time": result.server_time,
        "results": [
            {
                "operation_id": r.operation_id,
                "status": r.status,
                "record_id": r.record_id,
                "conflict_details": r.conflict_details,
                "error": r.error,
                "applied_at": r.applied_at,
            }
            for r in result.results
        ],
    })