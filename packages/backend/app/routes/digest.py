from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.digest import build_weekly_digest

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    anchor_raw = (request.args.get("date") or "").strip()
    currency = (request.args.get("currency") or "").strip().upper() or None

    try:
        anchor_date = date.fromisoformat(anchor_raw) if anchor_raw else date.today()
    except ValueError:
        return jsonify(error="invalid date"), 400

    return jsonify(build_weekly_digest(uid, anchor_date=anchor_date, currency=currency))
