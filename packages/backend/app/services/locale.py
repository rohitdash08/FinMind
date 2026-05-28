"""Locale-aware date, currency and number formatting for FinMind.

Supports:
- Currency formatting per locale (USD, EUR, GBP, JPY, CNY, etc.)
- Date formatting (short, medium, long, full)
- Number formatting with locale-specific separators
- User preference persistence
"""

import locale
import logging
from datetime import datetime, date
from typing import Optional

from flask import request, g
from flask_jwt_extended import get_jwt_identity, jwt_required

logger = logging.getLogger("finmind.locale")

# Locale registry with formatting rules
LOCALE_CONFIGS = {
    "en-US": {"currency": "USD", "symbol": "$", "decimal": ".", "thousands": ",", "date": "%m/%d/%Y", "position": "before"},
    "en-GB": {"currency": "GBP", "symbol": "\u00a3", "decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "position": "before"},
    "de-DE": {"currency": "EUR", "symbol": "\u20ac", "decimal": ",", "thousands": ".", "date": "%d.%m.%Y", "position": "after"},
    "fr-FR": {"currency": "EUR", "symbol": "\u20ac", "decimal": ",", "thousands": " ", "date": "%d/%m/%Y", "position": "after"},
    "ja-JP": {"currency": "JPY", "symbol": "\u00a5", "decimal": ".", "thousands": ",", "date": "%Y/%m/%d", "position": "before"},
    "zh-CN": {"currency": "CNY", "symbol": "\u00a5", "decimal": ".", "thousands": ",", "date": "%Y-%m-%d", "position": "before"},
    "zh-TW": {"currency": "TWD", "symbol": "NT$", "decimal": ".", "thousands": ",", "date": "%Y/%m/%d", "position": "before"},
    "ko-KR": {"currency": "KRW", "symbol": "\u20a9", "decimal": ".", "thousands": ",", "date": "%Y.%m.%d", "position": "before"},
    "pt-BR": {"currency": "BRL", "symbol": "R$", "decimal": ",", "thousands": ".", "date": "%d/%m/%Y", "position": "before"},
    "es-ES": {"currency": "EUR", "symbol": "\u20ac", "decimal": ",", "thousands": ".", "date": "%d/%m/%Y", "position": "after"},
    "hi-IN": {"currency": "INR", "symbol": "\u20b9", "decimal": ".", "thousands": ",", "date": "%d-%m-%Y", "position": "before"},
    "ar-SA": {"currency": "SAR", "symbol": "\u0631.\u0633", "decimal": ".", "thousands": ",", "date": "%Y/%m/%d", "position": "after"},
}

DEFAULT_LOCALE = "en-US"


def get_locale_config(locale_str: str | None = None) -> dict:
    """Get locale configuration, falling back to default."""
    if locale_str and locale_str in LOCALE_CONFIGS:
        return LOCALE_CONFIGS[locale_str]
    return LOCALE_CONFIGS[DEFAULT_LOCALE]


def format_currency(amount: float, locale_str: str | None = None, currency: str | None = None) -> str:
    """Format a number as currency according to locale.

    Args:
        amount: The numeric amount
        locale_str: Locale identifier (e.g., "en-US")
        currency: Override currency code (e.g., "EUR")

    Returns:
        Formatted currency string (e.g., "$1,234.56")
    """
    config = get_locale_config(locale_str)

    # Format the number with proper separators
    is_negative = amount < 0
    abs_amount = abs(amount)

    # Split into integer and decimal parts
    integer_part = int(abs_amount)
    decimal_part = round((abs_amount - integer_part) * 100)

    # Add thousands separators
    int_str = str(integer_part)
    sep = config["thousands"]
    groups = []
    while int_str:
        groups.append(int_str[-3:])
        int_str = int_str[:-3]
    formatted_int = sep.join(reversed(groups))

    # Add decimal part
    dec_str = f"{decimal_part:02d}"

    # Get symbol
    symbol = config["symbol"]

    # Build final string
    sign = "-" if is_negative else ""
    number = f"{formatted_int}{config['decimal']}{dec_str}"

    if config["position"] == "before":
        return f"{sign}{symbol}{number}"
    else:
        return f"{sign}{number} {symbol}"


def format_number(number: float, locale_str: str | None = None, decimals: int = 2) -> str:
    """Format a number with locale-specific separators.

    Args:
        number: The number to format
        locale_str: Locale identifier
        decimals: Number of decimal places

    Returns:
        Formatted number string (e.g., "1,234.56" or "1.234,56")
    """
    config = get_locale_config(locale_str)

    # Round to specified decimals
    formatted = f"{abs(number):.{decimals}f}"
    integer_str, decimal_str = formatted.split(".")

    # Add thousands separators
    sep = config["thousands"]
    groups = []
    while integer_str:
        groups.append(integer_str[-3:])
        integer_str = integer_str[:-3]
    result = sep.join(reversed(groups))

    if decimals > 0:
        result += config["decimal"] + decimal_str

    if number < 0:
        result = "-" + result

    return result


def format_date(d: date | datetime, locale_str: str | None = None, style: str = "medium") -> str:
    """Format a date according to locale.

    Args:
        d: Date or datetime object
        locale_str: Locale identifier
        style: "short", "medium", "long", or "full"

    Returns:
        Formatted date string
    """
    config = get_locale_config(locale_str)
    base_format = config["date"]

    if style == "short":
        # Remove year for short format
        base_format = base_format.replace("%Y", "%y")
    elif style == "long":
        base_format = base_format.replace("%Y", "%A, %B %d, %Y")
    elif style == "full":
        base_format = "%A, %B %d, %Y"

    if isinstance(d, datetime):
        d = d.date()
    return d.strftime(base_format)


def parse_locale_number(text: str, locale_str: str | None = None) -> float:
    """Parse a locale-formatted number string back to float.

    Args:
        text: Formatted number string (e.g., "1.234,56" in de-DE)
        locale_str: Locale identifier

    Returns:
        Float value
    """
    config = get_locale_config(locale_str)

    # Remove thousands separator, replace decimal separator
    cleaned = text.replace(config["thousands"], "").replace(config["decimal"], ".")
    return float(cleaned)


def get_supported_locales() -> list[dict]:
    """Return list of all supported locales with their configs."""
    return [
        {"locale": k, "currency": v["currency"], "symbol": v["symbol"], "date_format": v["date"]}
        for k, v in LOCALE_CONFIGS.items()
    ]
