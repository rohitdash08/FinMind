from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.sync import (
    sync_records,
    pull_since,
    ConflictStrategy,
)

sync_bp = Blueprint("sync", __name__, url_prefix="/sync")


@sync_bp.route("/push", methods=["POST"])
@jwt_required()
def push():
    """
    POST /sync/push
    Push local changes from client to server.
    Body:
    {
      entity_type: "expense" | "income" | "recurring_bill",
      strategy: "last_write_wins" | "server_wins" | "client_wins" | "manual",
      records: [
        {
          id: <int|null>,
          client_id: <string>,
          updated_at: <ISO8601>,
          deleted: <bool>,
          payload: { ...model fields }
        }
      ]
    }
    """
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    entity_type = body.get("entity_type")
    records = body.get("records")
    strategy_str = body.get("strategy", "last_write_wins")

    if not entity_type:
        return jsonify({"error": "entity_type required"}), 400
    if not records or not isinstance(records, list):
        return jsonify({"error": "records must be a non-empty list"}), 400
    if len(records) > 500:
        return jsonify({"error": "maximum 500 records per push"}), 400

    try:
        strategy = ConflictStrategy(strategy_str)
    except ValueError:
        return jsonify({"error": f"Invalid strategy. Valid: {[s.value for s in ConflictStrategy]}"}), 400

    try:
        report = sync_records(uid, entity_type, records, strategy)
        return jsonify(report), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@sync_bp.route("/pull", methods=["GET"])
@jwt_required()
def pull():
    """
    GET /sync/pull?entity_type=expense&since=<ISO8601>
    Fetch all server-side records modified after the given watermark.
    """
    uid = int(get_jwt_identity())
    entity_type = request.args.get("entity_type")
    since_str = request.args.get("since")

    if not entity_type:
        return jsonify({"error": "entity_type query param required"}), 400

    since = None
    if since_str:
        try:
            since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
        except ValueError:
            return jsonify({"error": "since must be ISO-8601 format"}), 400

    try:
        records = pull_since(uid, entity_type, since)
        return jsonify({
            "entity_type": entity_type,
            "count": len(records),
            "records": records,
            "server_time": datetime.utcnow().isoformat() + "Z",
        }), 200
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
