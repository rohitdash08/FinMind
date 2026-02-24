"""
locale.py — Locale formatting API endpoints.

GET  /locale/supported          List supported locale codes
GET  /locale/meta?locale=en_IN  Metadata for a locale
POST /locale/format             Format values in bulk
"""
from flask import Blueprint, jsonify, request
from ..services.locale_formatter import (
    format_currency,
    format_date,
    format_datetime,
    format_number,
    locale_meta,
    supported_locales,
)

bp = Blueprint("locale", __name__)


@bp.get("/supported")
def list_supported():
    """Return list of supported locale codes."""
    return jsonify({"locales": supported_locales()})


@bp.get("/meta")
def get_locale_meta():
    """Return metadata for a given locale (defaults to en_IN)."""
    locale = request.args.get("locale")
    return jsonify(locale_meta(locale))


@bp.post("/format")
def format_values():
    """
    Bulk-format a set of values in a given locale.

    Request body (JSON):
    {
      "locale": "de_DE",
      "values": [
        {"type": "currency", "amount": 1234.5, "currency": "EUR"},
        {"type": "number",   "value": 9876543.21, "decimal_places": 2},
        {"type": "date",     "value": "2026-02-24", "format": "long"},
        {"type": "datetime", "value": "2026-02-24T13:00:00", "format": "medium"}
      ]
    }

    Response:
    {
      "locale": "de_DE",
      "results": ["1.234,50 €", "9.876.543,21", "24. Februar 2026", "24.02.2026, 13:00:00"]
    }
    """
    body = request.get_json(silent=True) or {}
    locale = body.get("locale")
    values = body.get("values", [])

    if not isinstance(values, list):
        return jsonify(error="'values' must be a list"), 400

    results = []
    for item in values:
        kind = item.get("type", "")
        try:
            if kind == "currency":
                results.append(format_currency(
                    item.get("amount", 0),
                    item.get("currency", "INR"),
                    locale,
                ))
            elif kind == "number":
                results.append(format_number(
                    item.get("value", 0),
                    locale,
                    item.get("decimal_places", 2),
                ))
            elif kind == "date":
                results.append(format_date(
                    item.get("value", ""),
                    locale,
                    item.get("format", "medium"),
                ))
            elif kind == "datetime":
                results.append(format_datetime(
                    item.get("value", ""),
                    locale,
                    item.get("format", "medium"),
                ))
            else:
                results.append(None)
        except Exception as exc:
            results.append(f"error: {exc}")

    return jsonify({"locale": locale, "results": results})
