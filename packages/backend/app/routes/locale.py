"""Locale-aware formatting API."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.locale_formatting import (
    get_locale, update_locale, format_currency, format_date,
    format_number, get_supported_currencies, get_date_formats, get_number_formats,
)

bp = Blueprint("locale", __name__)


@bp.get("/")
@jwt_required()
def get_loc():
    uid = int(get_jwt_identity())
    return jsonify(get_locale(uid))


@bp.put("/")
@jwt_required()
def update():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        return jsonify(update_locale(uid, **data))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/format/currency")
@jwt_required()
def fmt_currency():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    amount = float(data.get("amount", 0))
    return jsonify({"formatted": format_currency(uid, amount)})


@bp.post("/format/date")
@jwt_required()
def fmt_date():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    d = date.fromisoformat(data.get("date", date.today().isoformat()))
    return jsonify({"formatted": format_date(uid, d)})


@bp.post("/format/number")
@jwt_required()
def fmt_number():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    return jsonify({"formatted": format_number(uid, float(data.get("value", 0)), int(data.get("decimals", 2)))})


@bp.get("/currencies")
@jwt_required()
def currencies():
    return jsonify(get_supported_currencies())


@bp.get("/date-formats")
@jwt_required()
def date_fmts():
    return jsonify(get_date_formats())


@bp.get("/number-formats")
@jwt_required()
def number_fmts():
    return jsonify(get_number_formats())
