"""
Locale-aware formatting REST API.

Endpoints:
  GET  /locale/locales         — List supported locales
  GET  /locale/info/<locale>    — Get locale details
  POST /locale/format/currency  — Format a currency amount
  POST /locale/format/number    — Format a number
  POST /locale/format/percent   — Format a percentage
  POST /locale/format/date      — Format a date
  GET  /locale/format/relative  — Get relative time string
"""

from datetime import date, datetime
from flask import Blueprint, jsonify, request

from ..services.locale_formatting import (
    SUPPORTED_LOCALES,
    format_currency_amount,
    format_date_locale,
    format_number,
    format_percentage,
    format_relative_time,
    format_time_locale,
    get_locale_info,
    resolve_locale,
)

bp = Blueprint("locale", __name__)


@bp.get("/locales")
def list_locales():
    """List all supported locales with display names."""
    return jsonify(
        {
            "locales": [
                {"code": code, "display_name": name}
                for code, name in sorted(SUPPORTED_LOCALES.items())
            ],
            "total": len(SUPPORTED_LOCALES),
        }
    )


@bp.get("/info/<locale>")
def locale_info(locale: str):
    """Get detailed information about a specific locale."""
    if locale not in SUPPORTED_LOCALES:
        return jsonify(error=f"Locale {locale!r} is not supported"), 404
    info = get_locale_info(locale)
    return jsonify(info)


@bp.post("/format/currency")
def format_currency():
    """Format a currency amount.

    JSON body:
      amount (required): number
      currency (required): ISO 4217 code, e.g. 'USD', 'INR'
      locale (optional): override auto-detection
      format_type (optional): 'standard', 'short', or 'name'
    """
    data = request.get_json()
    if not data or "amount" not in data or "currency" not in data:
        return jsonify(error="Fields 'amount' and 'currency' are required"), 400

    try:
        amount = float(data["amount"])
    except (ValueError, TypeError):
        return jsonify(error="'amount' must be a number"), 400

    currency = str(data["currency"]).upper()
    locale = data.get("locale")
    format_type = data.get("format_type")

    result = format_currency_amount(
        amount=amount,
        currency=currency,
        locale=locale,
        format_type=format_type,
    )
    resolved = resolve_locale(currency, locale)

    return jsonify(
        {
            "formatted": result,
            "amount": amount,
            "currency": currency,
            "locale": resolved,
        }
    )


@bp.post("/format/number")
def format_number_endpoint():
    """Format a number with locale-aware separators.

    JSON body:
      value (required): number
      locale (optional): override auto-detection
      currency (optional): for locale auto-detection
    """
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify(error="Field 'value' is required"), 400

    try:
        value = float(data["value"])
    except (ValueError, TypeError):
        return jsonify(error="'value' must be a number"), 400

    locale = data.get("locale")
    currency = data.get("currency")
    result = format_number(value=value, locale=locale, currency=currency)

    return jsonify(
        {
            "formatted": result,
            "value": value,
            "locale": locale or (resolve_locale(currency) if currency else "en_US"),
        }
    )


@bp.post("/format/percent")
def format_percent_endpoint():
    """Format a percentage.

    JSON body:
      value (required): number (0.15 = 15%)
      locale (optional): override auto-detection
      currency (optional): for locale auto-detection
    """
    data = request.get_json()
    if not data or "value" not in data:
        return jsonify(error="Field 'value' is required"), 400

    try:
        value = float(data["value"])
    except (ValueError, TypeError):
        return jsonify(error="'value' must be a number"), 400

    locale = data.get("locale")
    currency = data.get("currency")
    result = format_percentage(value=value, locale=locale, currency=currency)

    return jsonify(
        {
            "formatted": result,
            "value": value,
            "locale": locale or (resolve_locale(currency) if currency else "en_US"),
        }
    )


@bp.post("/format/date")
def format_date_endpoint():
    """Format a date.

    JSON body:
      date (required): ISO date string (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
      format_type (optional): 'short', 'medium', 'long', or 'full' (default: 'medium')
      locale (optional): override auto-detection
      currency (optional): for locale auto-detection
    """
    data = request.get_json()
    if not data or "date" not in data:
        return jsonify(error="Field 'date' is required"), 400

    date_str = str(data["date"])
    format_type = data.get("format_type", "medium")
    locale = data.get("locale")
    currency = data.get("currency")

    try:
        # Try datetime first, then date
        if "T" in date_str:
            parsed = datetime.fromisoformat(date_str)
        else:
            parsed = date.fromisoformat(date_str)
    except ValueError:
        return jsonify(error="'date' must be a valid ISO date string"), 400

    result = format_date_locale(
        value=parsed,
        format_type=format_type,
        locale=locale,
        currency=currency,
    )

    return jsonify(
        {
            "formatted": result,
            "date": date_str,
            "format_type": format_type,
            "locale": locale or (resolve_locale(currency) if currency else "en_US"),
        }
    )


@bp.get("/format/relative")
def format_relative_endpoint():
    """Get a relative time string.

    Query params:
      date (required): ISO date string
      reference (optional): ISO date string (defaults to now)
    """
    date_str = request.args.get("date")
    if not date_str:
        return jsonify(error="Query param 'date' is required"), 400

    try:
        if "T" in date_str:
            target = datetime.fromisoformat(date_str)
        else:
            target = date.fromisoformat(date_str)
    except ValueError:
        return jsonify(error="'date' must be a valid ISO date string"), 400

    ref_str = request.args.get("reference")
    reference = None
    if ref_str:
        try:
            if "T" in ref_str:
                reference = datetime.fromisoformat(ref_str)
            else:
                reference = date.fromisoformat(ref_str)
        except ValueError:
            return jsonify(error="'reference' must be a valid ISO date string"), 400

    result = format_relative_time(value=target, reference=reference)

    return jsonify({"formatted": result, "date": date_str})
