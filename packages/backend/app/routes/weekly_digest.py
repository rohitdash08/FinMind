from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date

from ..services.weekly_digest import compute_weekly_digest

bp = Blueprint("weekly_digest", __name__, url_prefix="/weekly-digest")


@bp.get("/")
@jwt_required()
def get_weekly_digest():
    """
    GET /weekly-digest/
    Query params:
      - date (optional): ISO date (YYYY-MM-DD) to anchor the week.
                         Defaults to current week.
    Returns a weekly financial summary with trends and insights.
    """
    user_id = int(get_jwt_identity())
    ref_date_str = request.args.get("date")
    ref_date = None
    if ref_date_str:
        try:
            ref_date = date.fromisoformat(ref_date_str)
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    digest = compute_weekly_digest(user_id, ref_date)
    return jsonify(digest), 200
