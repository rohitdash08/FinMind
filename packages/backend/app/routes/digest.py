"""Weekly digest API endpoint."""
from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import generate_weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_param = request.args.get("week")
    target_date = date.fromisoformat(week_param) if week_param else None
    return jsonify(generate_weekly_digest(uid, target_date))