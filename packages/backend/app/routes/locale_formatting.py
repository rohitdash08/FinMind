from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..services.locale_formatting import format_for_locale, list_supported_locales

bp = Blueprint("locale_formatting", __name__)


@bp.route("/format", methods=["GET"])
@jwt_required()
def format_locale():
    """
    GET /insights/format
    Query params:
      - locale: BCP 47 locale tag (default: en-US)
      - amount: float monetary amount (default: 1234.56)
      - number: float plain number (default: 9876543.21)
      - date: ISO 8601 date string YYYY-MM-DD (default: today)
    Returns locale-formatted representations of date, currency, and number.
    """
    locale = request.args.get("locale", "en-US")
    try:
        amount = float(request.args.get("amount", 1234.56))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    try:
        number = float(request.args.get("number", 9876543.21))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid number"}), 400

    date_str = request.args.get("date", None)

    result = format_for_locale(locale, amount, number, date_str)
    return jsonify({
        "locale": result.locale,
        "locale_name": result.locale_name,
        "currency_code": result.currency_code,
        "input": {
            "date": result.input_date,
            "amount": result.input_amount,
            "number": result.input_number,
        },
        "formatted": {
            "date": result.formatted_date,
            "date_short": result.formatted_date_short,
            "currency": result.formatted_currency,
            "number": result.formatted_number,
        },
    })


@bp.route("/locales", methods=["GET"])
@jwt_required()
def get_locales():
    """
    GET /insights/locales
    Returns list of all supported locales with metadata.
    """
    return jsonify({"supported_locales": list_supported_locales()})