"""Multi-currency expense tracking API."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.multi_currency import (
    get_user_currency, set_user_currency, set_exchange_rate,
    convert_amount, list_rates, multi_currency_summary,
)
import logging

bp = Blueprint("currency", __name__)
logger = logging.getLogger("finmind.currency")


@bp.get("/preference")
@jwt_required()
def get_pref():
    uid = int(get_jwt_identity())
    return jsonify(get_user_currency(uid))


@bp.put("/preference")
@jwt_required()
def update_pref():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("base_currency"):
        return jsonify({"error": "base_currency is required"}), 400
    try:
        result = set_user_currency(uid, data["base_currency"], data.get("display_currencies"))
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/rates")
@jwt_required()
def add_rate():
    data = request.get_json() or {}
    required = ["base_currency", "target_currency", "rate"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "base_currency, target_currency, and rate are required"}), 400
    try:
        rate_date = date.fromisoformat(data["date"]) if data.get("date") else None
        result = set_exchange_rate(data["base_currency"], data["target_currency"], float(data["rate"]), rate_date)
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/rates")
@jwt_required()
def get_rates():
    base = request.args.get("base")
    d = request.args.get("date")
    rate_date = date.fromisoformat(d) if d else None
    return jsonify(list_rates(base, rate_date))


@bp.post("/convert")
@jwt_required()
def convert():
    data = request.get_json() or {}
    required = ["amount", "from_currency", "to_currency"]
    if not all(data.get(k) for k in required):
        return jsonify({"error": "amount, from_currency, and to_currency are required"}), 400
    try:
        result = convert_amount(float(data["amount"]), data["from_currency"], data["to_currency"])
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/summary")
@jwt_required()
def summary():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not isinstance(data.get("expenses"), list):
        return jsonify({"error": "expenses array is required"}), 400
    return jsonify(multi_currency_summary(uid, data["expenses"]))
