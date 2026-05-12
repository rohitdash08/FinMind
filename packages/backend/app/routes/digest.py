"""Weekly digest routes."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import generate_weekly_digest

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly():
    """Get weekly financial digest for the authenticated user."""
    uid = int(get_jwt_identity())
    end_date_str = request.args.get("end_date")
    end_date = date.fromisoformat(end_date_str) if end_date_str else None
    digest = generate_weekly_digest(uid, end_date)
    return jsonify(digest=digest)
