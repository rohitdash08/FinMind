"""Multi-currency conversion endpoints."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services.currency import convert, get_supported_currencies, convert_all
import logging

bp = Blueprint("currency", __name__)
logger = logging.getLogger("finmind.currency")


@bp.get("/supported")
@jwt_required()
def supported():
    return jsonify(currencies=get_supported_currencies())


@bp.get("/convert")
@jwt_required()
def convert_endpoint():
    amount = request.args.get("amount")
    from_cur = request.args.get("from", "").strip()
    to_cur = request.args.get("to", "").strip()
    if not amount or not from_cur or not to_cur:
        return jsonify(error="amount, from, and to params required"), 400
    try:
        result = convert(float(amount), from_cur, to_cur)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(result)


@bp.get("/convert-all")
@jwt_required()
def convert_all_endpoint():
    amount = request.args.get("amount")
    from_cur = request.args.get("from", "").strip()
    if not amount or not from_cur:
        return jsonify(error="amount and from params required"), 400
    try:
        results = convert_all(float(amount), from_cur)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(conversions=results, base_amount=float(amount), base_currency=from_cur.upper())
