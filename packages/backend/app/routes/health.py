import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.health_score import calculate_health_score

bp = Blueprint("health", __name__)
logger = logging.getLogger("finmind.health_routes")


@bp.get("/score")
@jwt_required()
def health_score():
    """
    Get the financial health score for the current user.

    Query params:
        months (int, 1-12, default 3): Historical period for analysis

    Returns:
        {
            score: 0-100,
            grade: A/B/C/D/F,
            label: excellent/good/fair/needs_attention/poor,
            components: [{name, score, weight, weighted_score, label, detail}],
            insights: [str],
            calculated_at: YYYY-MM-DD
        }
    """
    uid = int(get_jwt_identity())
    try:
        months = min(12, max(1, int(request.args.get("months", 3))))
    except (ValueError, TypeError):
        return jsonify(error="months must be an integer between 1 and 12"), 400

    result = calculate_health_score(uid, months)
    logger.info("Health score uid=%s score=%.1f grade=%s", uid, result["score"], result["grade"])
    return jsonify(result)
