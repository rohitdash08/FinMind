from flask import Blueprint, jsonify, request

from ..services.i18n import (
    get_locale,
    list_locales,
    format_currency,
    format_date,
    format_number,
    detect_locale_from_headers,
)

bp = Blueprint("i18n", __name__)


@bp.get("/locales")
def locales():
    return jsonify(list_locales())


@bp.get("/locale")
def locale_info():
    locale_str = request.args.get("locale", "en-US")
    return jsonify(get_locale(locale_str))


@bp.post("/format/currency")
def fmt_currency():
    data = request.get_json() or {}
    amount = data.get("amount", 0)
    locale_str = data.get("locale", "en-US")
    currency_code = data.get("currency_code")
    return jsonify(formatted=format_currency(float(amount), locale_str, currency_code))


@bp.post("/format/date")
def fmt_date():
    data = request.get_json() or {}
    date_val = data.get("date", "")
    locale_str = data.get("locale", "en-US")
    style = data.get("style", "short")
    return jsonify(formatted=format_date(date_val, locale_str, style))


@bp.post("/format/number")
def fmt_number():
    data = request.get_json() or {}
    value = data.get("value", 0)
    locale_str = data.get("locale", "en-US")
    decimals = int(data.get("decimals", 2))
    return jsonify(formatted=format_number(float(value), locale_str, decimals))


@bp.post("/detect")
def detect():
    data = request.get_json() or {}
    accept_language = data.get("accept_language") or request.headers.get("Accept-Language")
    return jsonify(locale=detect_locale_from_headers(accept_language))
