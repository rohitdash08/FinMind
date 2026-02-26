"""Routes for weekly financial digest."""

from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.weekly_digest import DigestGenerator

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial summary for the authenticated user.

    Query params:
        date  – ISO date within the target week (default: today)
    """
    uid = int(get_jwt_identity())
    date_str = request.args.get("date")
    ref_date = None
    if date_str:
        try:
            ref_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify(error="invalid date format, use YYYY-MM-DD"), 400

    generator = DigestGenerator()
    digest = generator.generate(user_id=uid, reference_date=ref_date)
    return jsonify(digest.to_dict())
