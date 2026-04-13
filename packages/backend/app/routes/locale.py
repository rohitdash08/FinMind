"""Locale-aware date, currency and number formatting."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
import locale as loc
bp = Blueprint("locale", __name__)

SUPPORTED_LOCALES = {
    "en-US": {"currency": "USD", "date_format": "MM/DD/YYYY", "decimal": ".", "thousands": ","},
    "en-GB": {"currency": "GBP", "date_format": "DD/MM/YYYY", "decimal": ".", "thousands": ","},
    "en-IN": {"currency": "INR", "date_format": "DD/MM/YYYY", "decimal": ".", "thousands": ","},
    "de-DE": {"currency": "EUR", "date_format": "DD.MM.YYYY", "decimal": ",", "thousands": "."},
    "fr-FR": {"currency": "EUR", "date_format": "DD/MM/YYYY", "decimal": ",", "thousands": " "},
    "ja-JP": {"currency": "JPY", "date_format": "YYYY/MM/DD", "decimal": ".", "thousands": ","},
    "ar-SA": {"currency": "SAR", "date_format": "DD/MM/YYYY", "decimal": ".", "thousands": ","},
    "zh-CN": {"currency": "CNY", "date_format": "YYYY-MM-DD", "decimal": ".", "thousands": ","},
    "pt-BR": {"currency": "BRL", "date_format": "DD/MM/YYYY", "decimal": ",", "thousands": "."},
    "es-MX": {"currency": "MXN", "date_format": "DD/MM/YYYY", "decimal": ".", "thousands": ","},
}

@bp.get("/supported")
@jwt_required()
def supported():
    return jsonify(locales=list(SUPPORTED_LOCALES.keys()))

@bp.get("/config")
@jwt_required()
def get_config():
    locale_id = request.args.get("locale", "en-US")
    config = SUPPORTED_LOCALES.get(locale_id)
    if not config:
        return jsonify(error=f"unsupported locale: {locale_id}"), 400
    return jsonify(locale=locale_id, **config)

@bp.post("/format")
@jwt_required()
def format_value():
    data = request.get_json() or {}
    value = data.get("value")
    value_type = data.get("type", "currency")
    locale_id = data.get("locale", "en-US")
    if value is None:
        return jsonify(error="value required"), 400
    config = SUPPORTED_LOCALES.get(locale_id)
    if not config:
        return jsonify(error="unsupported locale"), 400
    
    if value_type == "currency":
        dec = config["decimal"]
        thou = config["thousands"]
        amt = float(value)
        integer = int(abs(amt))
        frac = abs(amt) - integer
        int_str = ""
        s = str(integer)
        for i, c in enumerate(reversed(s)):
            if i > 0 and i % 3 == 0:
                int_str = thou + int_str
            int_str = c + int_str
        formatted = f"{'-' if amt < 0 else ''}{config['currency']} {int_str}{dec}{int(frac*100):02d}"
    elif value_type == "number":
        formatted = f"{float(value):,.2f}".replace(",", config.get("thousands", ","))
    elif value_type == "date":
        formatted = str(value)
    else:
        formatted = str(value)
    
    return jsonify(original=value, formatted=formatted, locale=locale_id, type=value_type)
