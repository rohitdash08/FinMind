"""Locale-aware formatting API for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.locale import (
    format_currency,
    format_number,
    format_date,
    get_supported_locales,
    get_locale_config,
)
from datetime import date

bp = Blueprint("locale", __name__)


@bp.get("/locales")
def list_locales():
    """List all supported locales."""
    return jsonify(get_supported_locales())


@bp.post("/format")
@jwt_required()
def format_values():
    """Format values according to locale.

    Body: {
        "locale": "de-DE",
        "values": [
            {"type": "currency", "amount": 1234.56},
            {"type": "number", "value": 9876.54, "decimals": 2},
            {"type": "date", "date": "2024-06-15", "style": "medium"}
        ]
    }
    """
    data = request.get_json() or {}
    locale_str = data.get("locale", "en-US")
    values = data.get("values", [])
    results = []

    for v in values:
        vtype = v.get("type")
        try:
            if vtype == "currency":
                results.append({
                    "type": "currency",
                    "original": v["amount"],
                    "formatted": format_currency(v["amount"], locale_str),
                })
            elif vtype == "number":
                results.append({
                    "type": "number",
                    "original": v["value"],
                    "formatted": format_number(v["value"], locale_str, v.get("decimals", 2)),
                })
            elif vtype == "date":
                d = date.fromisoformat(v["date"])
                results.append({
                    "type": "date",
                    "original": v["date"],
                    "formatted": format_date(d, locale_str, v.get("style", "medium")),
                })
            else:
                results.append({"type": vtype, "error": "Unknown type"})
        except Exception as e:
            results.append({"type": vtype, "error": str(e)})

    return jsonify(locale=locale_str, results=results)
