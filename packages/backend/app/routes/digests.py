from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.weekly_digest import get_weekly_digest, list_digest_history
import logging

bp = Blueprint("digests", __name__)
logger = logging.getLogger("finmind.digests")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    week_param = request.args.get("week")
    ref_date = None
    if week_param:
        try:
            ref_date = date.fromisoformat(week_param)
        except ValueError:
            return jsonify(error="invalid week date, expected YYYY-MM-DD"), 400
    data = get_weekly_digest(uid, ref_date)
    logger.info("Weekly digest served user=%s week=%s", uid, data.get("week_start"))
    return jsonify(data)


@bp.get("/history")
@jwt_required()
def digest_history():
    uid = int(get_jwt_identity())
    try:
        limit = min(52, max(1, int(request.args.get("limit", "20"))))
    except ValueError:
        limit = 20
    data = list_digest_history(uid, limit)
    return jsonify(data)
