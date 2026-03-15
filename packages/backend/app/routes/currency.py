"""Multi-Currency & FX Conversion routes.

Endpoints:
  GET    /currency/list                  — list supported currencies
  POST   /currency/seed                  — seed default currencies
  POST   /currency/rates                 — set or update an exchange rate
  POST   /currency/rates/bulk            — set multiple rates at once
  GET    /currency/rates                 — list rates (with optional filters)
  GET    /currency/rates/<base>/<target> — get specific rate
  POST   /currency/convert               — convert an amount
  GET    /currency/summary               — multi-currency expense summary
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.currency import (
    list_currencies,
    seed_currencies,
    set_rate,
    get_rate,
    list_rates,
    bulk_set_rates,
    convert,
    multi_currency_summary,
)

bp = Blueprint("currency", __name__)


@bp.route("/list", methods=["GET"])
@jwt_required()
def currencies_list():
    """Return all supported currencies."""
    active = request.args.get("active", "true").lower() == "true"
    return jsonify(list_currencies(active_only=active)), 200


@bp.route("/seed", methods=["POST"])
@jwt_required()
def currencies_seed():
    """Seed default currencies into the database."""
    added = seed_currencies()
    return jsonify({"added": added, "message": f"{added} currencies seeded"}), 200


@bp.route("/rates", methods=["POST"])
@jwt_required()
def upsert_rate():
    """Create or update an exchange rate."""
    data = request.get_json(silent=True) or {}
    base = data.get("base_currency")
    target = data.get("target_currency")
    rate_val = data.get("rate")

    if not base or not target or rate_val is None:
        return jsonify({"error": "base_currency, target_currency, and rate required"}), 400

    try:
        rate_decimal = Decimal(str(rate_val))
        if rate_decimal <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return jsonify({"error": "rate must be a positive number"}), 400

    rate_date = None
    if data.get("rate_date"):
        try:
            rate_date = date.fromisoformat(data["rate_date"])
        except ValueError:
            return jsonify({"error": "Invalid rate_date format (use YYYY-MM-DD)"}), 400

    result = set_rate(base, target, rate_decimal, rate_date, data.get("source", "manual"))
    return jsonify(result), 200


@bp.route("/rates/bulk", methods=["POST"])
@jwt_required()
def bulk_rates():
    """Set multiple rates for a base currency at once.

    Body: { "base_currency": "USD", "rates": {"EUR": 0.92, "GBP": 0.79}, "rate_date": "..." }
    """
    data = request.get_json(silent=True) or {}
    base = data.get("base_currency")
    rates = data.get("rates")

    if not base or not rates or not isinstance(rates, dict):
        return jsonify({"error": "base_currency and rates dict required"}), 400

    rate_date = None
    if data.get("rate_date"):
        try:
            rate_date = date.fromisoformat(data["rate_date"])
        except ValueError:
            return jsonify({"error": "Invalid rate_date format"}), 400

    count = bulk_set_rates(base, rates, rate_date, data.get("source", "bulk"))
    return jsonify({"updated": count}), 200


@bp.route("/rates", methods=["GET"])
@jwt_required()
def rates_list():
    """List exchange rates with optional filters."""
    base = request.args.get("base")
    target = request.args.get("target")
    days = request.args.get("days", "30", type=int)
    return jsonify(list_rates(base, target, days)), 200


@bp.route("/rates/<base>/<target>", methods=["GET"])
@jwt_required()
def rate_detail(base: str, target: str):
    """Get a specific exchange rate."""
    rate_date = None
    if request.args.get("date"):
        try:
            rate_date = date.fromisoformat(request.args["date"])
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

    result = get_rate(base, target, rate_date)
    if not result:
        return jsonify({"error": f"No rate found for {base}/{target}"}), 404
    return jsonify(result), 200


@bp.route("/convert", methods=["POST"])
@jwt_required()
def convert_amount():
    """Convert an amount between currencies.

    Body: { "amount": 1000, "from": "INR", "to": "USD" }
    """
    data = request.get_json(silent=True) or {}
    amount_raw = data.get("amount")
    from_cur = data.get("from") or data.get("from_currency")
    to_cur = data.get("to") or data.get("to_currency")

    if amount_raw is None or not from_cur or not to_cur:
        return jsonify({"error": "amount, from, and to are required"}), 400

    try:
        amount = Decimal(str(amount_raw))
    except (InvalidOperation, ValueError):
        return jsonify({"error": "Invalid amount"}), 400

    rate_date = None
    if data.get("date"):
        try:
            rate_date = date.fromisoformat(data["date"])
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400

    result = convert(amount, from_cur, to_cur, rate_date)
    if result is None:
        return jsonify({"error": f"No exchange rate available for {from_cur} → {to_cur}"}), 404
    return jsonify(result), 200


@bp.route("/summary", methods=["GET"])
@jwt_required()
def currency_summary():
    """Multi-currency expense summary for current user.

    Optional ?target=USD to override preferred currency.
    """
    uid = get_jwt_identity()
    target = request.args.get("target")
    result = multi_currency_summary(uid, target)
    if result is None:
        return jsonify({"error": "User not found"}), 404
    return jsonify(result), 200
