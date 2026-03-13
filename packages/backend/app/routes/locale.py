"""
Locale-aware formatting routes (Issue #131).

Endpoints:
  GET  /locale/supported              → list supported locales
  GET  /locale/info?locale=de_DE      → metadata for a locale
  POST /locale/format                 → format values with a given locale
  GET  /auth/me already returns preferred_locale
  PATCH /auth/me already handles preferred_locale (wired in auth.py)
"""

import logging
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from ..services.locale_fmt import (
    SUPPORTED_LOCALES,
    format_currency,
    format_date,
    format_datetime,
    format_number,
    get_locale_info,
)

bp = Blueprint("locale", __name__)
logger = logging.getLogger("finmind.locale")


@bp.get("/supported")
def supported_locales():
    """List all supported locales with their metadata."""
    return jsonify([get_locale_info(loc) for loc in SUPPORTED_LOCALES])


@bp.get("/info")
def locale_info():
    """Return metadata for a specific locale."""
    locale = request.args.get("locale", "en_IN")
    return jsonify(get_locale_info(locale))


@bp.post("/format")
@jwt_required()
def format_values():
    """
    Format one or more values using the specified (or user's preferred) locale.

    Request body:
    {
        "locale": "de_DE",          // optional — falls back to user's preferred_locale
        "currency": "EUR",          // optional — falls back to user's preferred_currency
        "amounts": [1234.56],       // list of amounts to format as currency
        "numbers": [9876543],       // list of plain numbers to format
        "dates": ["2026-03-14"],    // list of ISO dates to format
        "date_style": "medium"      // short|medium|long|iso
    }
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    data = request.get_json(silent=True) or {}
    locale = data.get("locale") or user.preferred_locale or "en_IN"
    currency = (data.get("currency") or user.preferred_currency or "INR").upper()
    date_style = data.get("date_style", "medium")

    result: dict = {"locale": locale, "currency": currency}

    if "amounts" in data:
        amounts = data["amounts"]
        if not isinstance(amounts, list):
            return jsonify(error="amounts must be a list"), 400
        result["formatted_amounts"] = [
            format_currency(a, currency, locale) for a in amounts
        ]

    if "numbers" in data:
        numbers = data["numbers"]
        if not isinstance(numbers, list):
            return jsonify(error="numbers must be a list"), 400
        result["formatted_numbers"] = [
            format_number(n, locale) for n in numbers
        ]

    if "dates" in data:
        dates = data["dates"]
        if not isinstance(dates, list):
            return jsonify(error="dates must be a list"), 400
        result["formatted_dates"] = [
            format_date(d, locale, date_style) for d in dates
        ]

    return jsonify(result)


@bp.get("/preview")
@jwt_required()
def preview():
    """
    Preview formatting for the authenticated user's locale + currency settings.
    Useful for frontend settings pages.
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="not found"), 404

    locale = user.preferred_locale or "en_IN"
    currency = user.preferred_currency or "INR"
    sample_amount = 1234567.89
    sample_date = datetime(2026, 3, 14)

    return jsonify({
        "locale": locale,
        "currency": currency,
        "examples": {
            "currency": format_currency(sample_amount, currency, locale),
            "number": format_number(sample_amount, locale),
            "date_short": format_date(sample_date.date(), locale, "short"),
            "date_medium": format_date(sample_date.date(), locale, "medium"),
            "date_long": format_date(sample_date.date(), locale, "long"),
            "datetime": format_datetime(sample_date, locale, "medium"),
        },
        "locale_info": get_locale_info(locale),
    })
