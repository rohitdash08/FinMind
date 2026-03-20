from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.financial_health_score import get_financial_health_score

bp = Blueprint("financial_health_score", __name__)


@bp.route("/health-score", methods=["GET"])
@jwt_required()
def financial_health_score():
    """
    GET /insights/health-score
    Query params:
      - months: int (1-24, default 6) — history window for analysis
    Returns a composite financial health score with per-dimension breakdown.
    """
    user_id = get_jwt_identity()
    try:
        months = int(request.args.get("months", 6))
    except (ValueError, TypeError):
        return jsonify({"error": "months must be an integer"}), 400

    if months < 1 or months > 24:
        return jsonify({"error": "months must be between 1 and 24"}), 400

    result = get_financial_health_score(user_id, months)
    return jsonify({
        "overall_score": result.overall_score,
        "grade": result.grade,
        "summary": result.summary,
        "months_analyzed": result.months_analyzed,
        "computed_at": result.computed_at,
        "dimensions": [
            {
                "name": d.name,
                "score": d.score,
                "weight": d.weight,
                "weighted_score": d.weighted_score,
                "explanation": d.explanation,
            }
            for d in result.dimensions
        ],
    })