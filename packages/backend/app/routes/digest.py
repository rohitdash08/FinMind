"""Weekly digest API route."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date
from ..services.weekly_digest import generate_weekly_digest

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    ref = request.args.get("ref_date")
    ref_date = date.fromisoformat(ref) if ref else None
    digest = generate_weekly_digest(uid, ref_date)
    return jsonify(digest)
