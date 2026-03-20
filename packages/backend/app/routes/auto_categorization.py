from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.auto_categorization import auto_categorize_batch, get_category_suggestion

bp = Blueprint("auto_categorization", __name__)


@bp.route("/categorize-suggest", methods=["GET"])
@jwt_required()
def suggest_category():
    """
    GET /insights/categorize-suggest?description=<text>
    Returns category suggestion with confidence score for a given description.
    Does not modify any data.
    """
    user_id = get_jwt_identity()
    description = request.args.get("description", "").strip()
    if not description:
        return jsonify({"error": "description is required"}), 400

    result = get_category_suggestion(user_id, description)
    return jsonify(result)


@bp.route("/auto-categorize", methods=["POST"])
@jwt_required()
def auto_categorize():
    """
    POST /insights/auto-categorize
    Body (optional JSON): { "min_confidence": 0.75 }
    Applies automatic category assignments to all uncategorized expenses.
    Only assigns when confidence >= min_confidence (default 0.75).
    """
    user_id = get_jwt_identity()
    body = request.get_json(silent=True) or {}
    min_confidence = float(body.get("min_confidence", 0.75))
    min_confidence = max(0.0, min(1.0, min_confidence))

    result = auto_categorize_batch(user_id, min_confidence)
    return jsonify(result)