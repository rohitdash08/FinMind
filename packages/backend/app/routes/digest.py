"""Smart digest routes — weekly financial summaries with trends."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import digest as digest_service

bp = Blueprint("digest", __name__)


@bp.route("", methods=["GET"])
@jwt_required()
def get_digest():
    """Generate or retrieve digest for the current period."""
    user_id = get_jwt_identity()
    period = request.args.get("period", "weekly")
    if period not in ("weekly", "monthly"):
        return jsonify({"error": "period must be 'weekly' or 'monthly'"}), 400

    data = digest_service.generate_digest(user_id, period=period)
    return jsonify(data), 200


@bp.route("/history", methods=["GET"])
@jwt_required()
def get_digest_history():
    """Return historical digests."""
    user_id = get_jwt_identity()
    limit = request.args.get("limit", 10, type=int)
    period = request.args.get("period")

    data = digest_service.get_digest_history(user_id, limit=limit, period=period)
    return jsonify(data), 200


@bp.route("/generate", methods=["POST"])
@jwt_required()
def force_generate():
    """Force generate a digest for a specific period."""
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    period = body.get("period", "weekly")
    reference_date_str = body.get("reference_date")

    if period not in ("weekly", "monthly"):
        return jsonify({"error": "period must be 'weekly' or 'monthly'"}), 400

    reference_date = None
    if reference_date_str:
        try:
            from datetime import date

            reference_date = date.fromisoformat(reference_date_str)
        except ValueError:
            return jsonify({"error": "Invalid reference_date format"}), 400

    data = digest_service.generate_digest(
        user_id, period=period, reference_date=reference_date
    )
    return jsonify(data), 201
