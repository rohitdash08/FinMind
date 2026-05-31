from decimal import Decimal, InvalidOperation
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.overspend_warnings import set_budget, get_budgets, delete_budget, check_warnings
import logging

bp = Blueprint("overspend_warnings", __name__)
logger = logging.getLogger("finmind.overspend")


@bp.get("/budgets")
@jwt_required()
def list_budgets():
    uid = int(get_jwt_identity())
    return jsonify(get_budgets(uid))


@bp.post("/budgets")
@jwt_required()
def create_budget():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    category_id = data.get("category_id")
    monthly_limit = data.get("monthly_limit")
    if not category_id or monthly_limit is None:
        return jsonify(error="category_id and monthly_limit required"), 400
    try:
        limit = Decimal(str(monthly_limit)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        return jsonify(error="invalid monthly_limit"), 400
    threshold = Decimal(str(data.get("warning_threshold_pct", 80)))
    result = set_budget(uid, int(category_id), limit, threshold)
    return jsonify(result), 201


@bp.delete("/budgets/<int:budget_id>")
@jwt_required()
def remove_budget(budget_id: int):
    uid = int(get_jwt_identity())
    if not delete_budget(uid, budget_id):
        return jsonify(error="not found"), 404
    return jsonify(message="deleted")


@bp.get("/warnings")
@jwt_required()
def warnings():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or "").strip() or None
    return jsonify(check_warnings(uid, ym))
