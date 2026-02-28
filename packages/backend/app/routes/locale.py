"""Locale formatting API routes."""

from datetime import datetime
from flask import Blueprint, jsonify, request
from app.services.locale_formatting import (
    format_currency,
    format_number,
    format_percent,
    format_date,
    format_datetime,
    format_relative_time,
    get_supported_locales,
    get_currency_for_locale,
    DEFAULT_LOCALE,
)

locale_bp = Blueprint("locale", __name__)


@locale_bp.route("/locales", methods=["GET"])
def list_locales():
    """List supported locales with their default currencies."""
    locales = get_supported_locales()
    return jsonify(
        [{"locale": loc, "currency": get_currency_for_locale(loc)} for loc in locales]
    )


@locale_bp.route("/format/currency", methods=["POST"])
def api_format_currency():
    """Format amount as locale-aware currency.

    Body: {"amount": 1234.56, "currency": "USD", "locale": "en_US"}
    """
    data = request.get_json() or {}
    amount = data.get("amount")
    if amount is None:
        return jsonify({"error": "amount is required"}), 400
    try:
        amount = float(amount)
    except (ValueError, TypeError):
        return jsonify({"error": "amount must be a number"}), 400

    locale_str = data.get("locale", DEFAULT_LOCALE)
    currency = data.get("currency")

    try:
        result = format_currency(amount, currency=currency, locale_str=locale_str)
        return jsonify({"formatted": result, "amount": amount, "locale": locale_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@locale_bp.route("/format/number", methods=["POST"])
def api_format_number():
    """Format number with locale-aware separators.

    Body: {"value": 1234567.89, "decimal_places": 2, "locale": "de_DE"}
    """
    data = request.get_json() or {}
    value = data.get("value")
    if value is None:
        return jsonify({"error": "value is required"}), 400
    try:
        value = float(value)
    except (ValueError, TypeError):
        return jsonify({"error": "value must be a number"}), 400

    locale_str = data.get("locale", DEFAULT_LOCALE)
    decimal_places = data.get("decimal_places")

    try:
        result = format_number(value, decimal_places=decimal_places, locale_str=locale_str)
        return jsonify({"formatted": result, "value": value, "locale": locale_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@locale_bp.route("/format/percent", methods=["POST"])
def api_format_percent():
    """Format value as locale-aware percentage.

    Body: {"value": 0.156, "decimal_places": 1, "locale": "en_US"}
    """
    data = request.get_json() or {}
    value = data.get("value")
    if value is None:
        return jsonify({"error": "value is required"}), 400
    try:
        value = float(value)
    except (ValueError, TypeError):
        return jsonify({"error": "value must be a number"}), 400

    locale_str = data.get("locale", DEFAULT_LOCALE)
    decimal_places = data.get("decimal_places", 1)

    try:
        result = format_percent(value, decimal_places=decimal_places, locale_str=locale_str)
        return jsonify({"formatted": result, "value": value, "locale": locale_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@locale_bp.route("/format/date", methods=["POST"])
def api_format_date():
    """Format date string with locale-aware pattern.

    Body: {"date": "2026-02-28", "format": "long", "locale": "zh_CN"}
    """
    data = request.get_json() or {}
    date_str = data.get("date")
    if not date_str:
        return jsonify({"error": "date is required"}), 400

    locale_str = data.get("locale", DEFAULT_LOCALE)
    fmt = data.get("format", "medium")

    try:
        dt = datetime.fromisoformat(date_str)
        result = format_datetime(dt, format=fmt, locale_str=locale_str)
        return jsonify({"formatted": result, "date": date_str, "locale": locale_str})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
