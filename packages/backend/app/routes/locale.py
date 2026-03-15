"""Routes for locale-aware formatting preferences and utilities."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.locale_formatting import (
    get_user_locale_preferences,
    update_user_locale_preferences,
    get_available_locales,
    get_supported_currencies,
    get_formatting_preview,
    format_number,
    format_currency,
    format_date,
    format_percentage,
    COMMON_TIMEZONES,
)

bp = Blueprint("locale", __name__)


@bp.route("/preferences", methods=["GET"])
@jwt_required()
def get_preferences():
    """Get current user's locale preferences."""
    user_id = int(get_jwt_identity())
    prefs = get_user_locale_preferences(user_id)
    return jsonify(prefs), 200


@bp.route("/preferences", methods=["PUT"])
@jwt_required()
def update_preferences():
    """Update current user's locale preferences.

    Accepts JSON body with any of:
    - locale: string (e.g., 'en_US', 'de_DE')
    - timezone: string (e.g., 'America/New_York')
    - date_format: 'short' | 'medium' | 'long' | 'iso'
    - number_format: 'standard' | 'compact'
    - currency_display: 'symbol' | 'code' | 'name'
    - currency: ISO 4217 currency code
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    if not data:
        return jsonify({"error": "No preferences provided"}), 400

    result = update_user_locale_preferences(user_id, data)
    if result is None:
        return jsonify({"error": "User not found"}), 404

    return jsonify(result), 200


@bp.route("/locales", methods=["GET"])
@jwt_required()
def list_locales():
    """List all available locales with sample formatting."""
    locales = get_available_locales()
    return jsonify({"locales": locales, "count": len(locales)}), 200


@bp.route("/currencies", methods=["GET"])
@jwt_required()
def list_currencies():
    """List all supported currencies with symbols and samples."""
    currencies = get_supported_currencies()
    return jsonify({"currencies": currencies, "count": len(currencies)}), 200


@bp.route("/timezones", methods=["GET"])
@jwt_required()
def list_timezones():
    """List all common timezones."""
    return jsonify({"timezones": COMMON_TIMEZONES, "count": len(COMMON_TIMEZONES)}), 200


@bp.route("/preview", methods=["POST"])
@jwt_required()
def preview_formatting():
    """Preview formatting with given locale/currency settings.

    Accepts JSON body with:
    - locale: string (required)
    - currency: string (optional, default 'USD')
    - currency_display: string (optional, default 'symbol')
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    locale = data.get("locale", "en_US")
    currency = data.get("currency", "USD")
    display = data.get("currency_display", "symbol")

    preview = get_formatting_preview(locale, currency, display)
    return jsonify(preview), 200


@bp.route("/format/number", methods=["POST"])
@jwt_required()
def format_number_endpoint():
    """Format a number with locale settings.

    Accepts JSON body:
    - value: number (required)
    - locale: string (optional)
    - decimal_places: int (optional)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    value = data.get("value")
    if value is None:
        return jsonify({"error": "value is required"}), 400

    locale = data.get("locale", "en_US")
    decimal_places = data.get("decimal_places", 2)

    formatted = format_number(value, locale, decimal_places)
    return jsonify({"formatted": formatted, "original": value}), 200


@bp.route("/format/currency", methods=["POST"])
@jwt_required()
def format_currency_endpoint():
    """Format a currency amount with locale settings.

    Accepts JSON body:
    - amount: number (required)
    - currency: string (optional, default 'INR')
    - locale: string (optional)
    - display: 'symbol' | 'code' | 'name' (optional)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    amount = data.get("amount")
    if amount is None:
        return jsonify({"error": "amount is required"}), 400

    currency = data.get("currency", "INR")
    locale = data.get("locale", "en_US")
    display = data.get("display", "symbol")

    formatted = format_currency(amount, currency, locale, display)
    return jsonify({"formatted": formatted, "original": amount}), 200


@bp.route("/format/date", methods=["POST"])
@jwt_required()
def format_date_endpoint():
    """Format a date with locale settings.

    Accepts JSON body:
    - date: string ISO date (required)
    - locale: string (optional)
    - style: 'short' | 'medium' | 'long' | 'iso' (optional)
    - relative: boolean (optional)
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    date_str = data.get("date")
    if not date_str:
        return jsonify({"error": "date is required"}), 400

    locale = data.get("locale", "en_US")
    style = data.get("style", "medium")
    relative = data.get("relative", False)

    formatted = format_date(date_str, locale, style, relative)
    return jsonify({"formatted": formatted, "original": date_str}), 200
