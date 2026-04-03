"""Multi-currency FX conversion routes for FinMind (#95)."""
import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import date
from ..services.fx import convert_amount, get_exchange_rate, list_supported_currencies, normalize_to_base

bp = Blueprint("fx", __name__)
logger = logging.getLogger("finmind.fx_routes")


@bp.get("/rate")
@jwt_required()
def get_rate():
    """
    Get exchange rate between two currencies.

    Query params:
        from (str): Source currency code (e.g. USD)
        to (str): Target currency code (e.g. INR)
        date (str, optional): ISO date for historical rate (defaults to today)

    Returns: { "from_currency", "to_currency", "rate", "date", "source" }
    """
    from_currency = (request.args.get("from") or "").strip().upper()
    to_currency = (request.args.get("to") or "").strip().upper()
    date_str = request.args.get("date")

    if not from_currency or not to_currency:
        return jsonify(error="from and to query parameters are required"), 400

    target_date = None
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify(error="date must be in YYYY-MM-DD format"), 400

    try:
        result = get_exchange_rate(from_currency, to_currency, target_date)
        return jsonify(result)
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.post("/convert")
@jwt_required()
def convert():
    """
    Convert an amount from one currency to another.

    Body: { "amount": 100.0, "from": "USD", "to": "INR", "date": "2026-04-03" }
    Returns: { "original_amount", "converted_amount", "from_currency", "to_currency", "rate", "date", "source" }
    """
    data = request.get_json() or {}
    amount = data.get("amount")
    from_currency = (data.get("from") or "").strip().upper()
    to_currency = (data.get("to") or "").strip().upper()
    date_str = data.get("date")

    if amount is None or not from_currency or not to_currency:
        return jsonify(error="amount, from, and to are required"), 400

    try:
        amount = float(amount)
        if amount < 0:
            return jsonify(error="amount must be non-negative"), 400
    except (ValueError, TypeError):
        return jsonify(error="amount must be a number"), 400

    target_date = None
    if date_str:
        try:
            target_date = date.fromisoformat(date_str)
        except ValueError:
            return jsonify(error="date must be in YYYY-MM-DD format"), 400

    try:
        result = convert_amount(amount, from_currency, to_currency, target_date)
        logger.info("FX convert %s %s->%s = %s", amount, from_currency, to_currency, result["converted_amount"])
        return jsonify(result)
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.post("/normalize")
@jwt_required()
def normalize():
    """
    Normalize multiple amounts to a base currency for analytics.

    Body: {
        "amounts": [{"amount": 100, "currency": "USD"}, {"amount": 5000, "currency": "INR"}],
        "base_currency": "INR"
    }
    Returns: List with base_amount and rate added to each entry
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amounts = data.get("amounts", [])
    base_currency = (data.get("base_currency") or "INR").strip().upper()

    if not isinstance(amounts, list):
        return jsonify(error="amounts must be a list"), 400

    if len(amounts) > 500:
        return jsonify(error="maximum 500 amounts per request"), 400

    try:
        results = normalize_to_base(uid, amounts, base_currency)
        return jsonify(results)
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.get("/currencies")
@jwt_required()
def currencies():
    """List all supported currency codes."""
    result = list_supported_currencies()
    return jsonify(currencies=result, count=len(result))

