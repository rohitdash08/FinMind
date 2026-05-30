import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.spending_breakdown import (
    get_spending_breakdown,
    get_spending_trends,
    update_spending_category,
)

bp = Blueprint("spending", __name__)
logger = logging.getLogger("finmind.spending")


@bp.get("/breakdown")
@jwt_required()
def spending_breakdown():
    uid = int(get_jwt_identity())
    ym = request.args.get("month") or None
    breakdown = get_spending_breakdown(uid, ym)
    return jsonify(breakdown)


@bp.get("/trends")
@jwt_required()
def spending_trends():
    uid = int(get_jwt_identity())
    months = request.args.get("months", 6, type=int)
    months = max(1, min(months, 24))
    trends = get_spending_trends(uid, months=months)
    return jsonify(trends)


@bp.patch("/categories/<int:category_id>")
@jwt_required()
def update_category_classification(category_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    is_essential = data.get("is_essential")
    if is_essential is None:
        return jsonify(error="is_essential required"), 400
    if not update_spending_category(uid, category_id, bool(is_essential)):
        return jsonify(error="not found"), 404
    return jsonify(message="updated"), 200
