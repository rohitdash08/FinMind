from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date
from ..services.monthly_review import get_monthly_review

bp = Blueprint("monthly_review", __name__)


@bp.route("/monthly-review", methods=["GET"])
@jwt_required()
def monthly_review():
    """
    GET /insights/monthly-review?year=2026&month=3
    Returns a guided 4-section monthly financial review with action items.
    Defaults to current month.
    """
    user_id = get_jwt_identity()
    today = date.today()

    try:
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
    except (ValueError, TypeError):
        return jsonify({"error": "year and month must be integers"}), 400

    if not (1 <= month <= 12):
        return jsonify({"error": "month must be 1-12"}), 400

    result = get_monthly_review(user_id, year, month)
    return jsonify({
        "review_month": result.review_month,
        "overall_score": result.overall_score,
        "grade": result.grade,
        "generated_at": result.generated_at,
        "action_items": result.action_items,
        "sections": [
            {
                "id": s.section_id,
                "title": s.title,
                "score": s.score,
                "summary": s.summary,
                "data": s.data,
                "insights": s.insights,
            }
            for s in result.sections
        ],
    })