"""
Locale formatting API route.
Issue #131: Expose locale-aware formatting utilities via API.
Allows frontend to request server-formatted values in user's locale.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User
from ..services.locale_format import (
    format_currency,
    format_date,
    format_number,
    get_supported_locales,
    get_supported_currencies,
)
from datetime import date as date_cls
import logging

bp = Blueprint("locale", __name__)
logger = logging.getLogger("finmind.locale")


@bp.get("/supported")
def supported():
    """Return supported locales and currencies."""
    return jsonify({
        "locales": get_supported_locales(),
        "currencies": get_supported_currencies(),
    })


@bp.post("/format")
@jwt_required()
def format_value():
    """
    Format a value (number, currency, or date) using locale-aware formatting.

    Request body:
      {
        "type": "currency" | "number" | "date",
        "value": <number or ISO date string>,
        "locale": "en-US",       // optional, uses user preferred if omitted
        "currency": "USD",       // required for type=currency
        "style": "medium",       // for type=date: "short"|"medium"|"long"|"iso"
        "decimals": 2            // optional for type=number
      }

    Returns:
      {"formatted": "..."}
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    fmt_type = data.get("type", "currency")
    value = data.get("value")
    style = data.get("style", "medium")

    # Resolve locale: request > user preference > default
    locale = data.get("locale")
    if not locale:
        user = db.session.get(User, uid)
        locale = getattr(user, "preferred_locale", None) or "en-US"

    try:
        if fmt_type == "currency":
            currency_code = data.get("currency", "USD")
            show_code = bool(data.get("show_code", False))
            amount = float(value)
            formatted = format_currency(amount, currency_code, locale=locale, show_code=show_code)
        elif fmt_type == "number":
            decimals = int(data.get("decimals", 2))
            formatted = format_number(float(value), locale=locale, decimals=decimals)
        elif fmt_type == "date":
            parsed = date_cls.fromisoformat(str(value))
            formatted = format_date(parsed, locale=locale, style=style)
        else:
            return jsonify(error=f"unsupported type: {fmt_type}"), 400
    except (ValueError, TypeError) as exc:
        return jsonify(error=f"invalid value: {exc}"), 400

    return jsonify({"formatted": formatted, "locale": locale, "type": fmt_type})


@bp.post("/format-batch")
@jwt_required()
def format_batch():
    """
    Format multiple values in one request.

    Request body:
      {
        "locale": "en-US",
        "items": [
          {"type": "currency", "value": 1234.56, "currency": "USD"},
          {"type": "date", "value": "2026-04-03", "style": "long"},
          {"type": "number", "value": 9876543.21, "decimals": 0}
        ]
      }

    Returns:
      {"results": ["$1,234.56", "April 3, 2026", "9,876,543"]}
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    locale = data.get("locale", "en-US")
    items = data.get("items", [])

    if not isinstance(items, list) or len(items) > 100:
        return jsonify(error="items must be a list of up to 100"), 400

    results = []
    for item in items:
        fmt_type = item.get("type", "currency")
        value = item.get("value")
        try:
            if fmt_type == "currency":
                results.append(format_currency(
                    float(value),
                    item.get("currency", "USD"),
                    locale=item.get("locale", locale),
                    show_code=bool(item.get("show_code", False)),
                ))
            elif fmt_type == "number":
                results.append(format_number(
                    float(value),
                    locale=item.get("locale", locale),
                    decimals=int(item.get("decimals", 2)),
                ))
            elif fmt_type == "date":
                parsed = date_cls.fromisoformat(str(value))
                results.append(format_date(
                    parsed,
                    locale=item.get("locale", locale),
                    style=item.get("style", "medium"),
                ))
            else:
                results.append(None)
        except (ValueError, TypeError):
            results.append(None)

    return jsonify({"results": results, "locale": locale})