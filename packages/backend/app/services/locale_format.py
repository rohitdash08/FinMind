"""
Locale-aware formatting service for FinMind.
Issue #131: Improve global usability with locale-aware date, currency & number formatting.

Supports formatting for:
- Dates: multiple locale styles (short, medium, long, ISO)
- Currency: proper symbols, decimal places, and thousands separators by locale
- Numbers: thousands separators and decimal separators by locale
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math


# Locale configuration: (decimal_sep, thousands_sep, currency_symbol_position)
_LOCALE_CONFIG = {
    # Americas
    "en-US": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "en-CA": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "pt-BR": {"decimal": ",", "thousands": ".", "symbol_before": True},
    "es-MX": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "es-AR": {"decimal": ",", "thousands": ".", "symbol_before": True},
    # Europe
    "en-GB": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "de-DE": {"decimal": ",", "thousands": ".", "symbol_before": False},
    "fr-FR": {"decimal": ",", "thousands": "\u00a0", "symbol_before": False},
    "es-ES": {"decimal": ",", "thousands": ".", "symbol_before": False},
    "it-IT": {"decimal": ",", "thousands": ".", "symbol_before": False},
    "nl-NL": {"decimal": ",", "thousands": ".", "symbol_before": False},
    "pl-PL": {"decimal": ",", "thousands": "\u00a0", "symbol_before": False},
    "ru-RU": {"decimal": ",", "thousands": "\u00a0", "symbol_before": False},
    "sv-SE": {"decimal": ",", "thousands": "\u00a0", "symbol_before": False},
    "nb-NO": {"decimal": ",", "thousands": "\u00a0", "symbol_before": False},
    "da-DK": {"decimal": ",", "thousands": ".", "symbol_before": False},
    # Asia
    "en-IN": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "hi-IN": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "ja-JP": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "zh-CN": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "zh-TW": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "ko-KR": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "ar-SA": {"decimal": ".", "thousands": ",", "symbol_before": False},
    "tr-TR": {"decimal": ",", "thousands": ".", "symbol_before": False},
    "th-TH": {"decimal": ".", "thousands": ",", "symbol_before": True},
    "id-ID": {"decimal": ",", "thousands": ".", "symbol_before": True},
    # Default fallback
    "default": {"decimal": ".", "thousands": ",", "symbol_before": True},
}

# Currency metadata: (symbol, decimal_places, thousands_grouping)
_CURRENCY_META = {
    "USD": {"symbol": "$", "decimals": 2},
    "EUR": {"symbol": "€", "decimals": 2},
    "GBP": {"symbol": "£", "decimals": 2},
    "INR": {"symbol": "₹", "decimals": 2},
    "JPY": {"symbol": "¥", "decimals": 0},
    "CNY": {"symbol": "¥", "decimals": 2},
    "KRW": {"symbol": "₩", "decimals": 0},
    "CAD": {"symbol": "CA$", "decimals": 2},
    "AUD": {"symbol": "A$", "decimals": 2},
    "NZD": {"symbol": "NZ$", "decimals": 2},
    "CHF": {"symbol": "Fr.", "decimals": 2},
    "SEK": {"symbol": "kr", "decimals": 2},
    "NOK": {"symbol": "kr", "decimals": 2},
    "DKK": {"symbol": "kr.", "decimals": 2},
    "HKD": {"symbol": "HK$", "decimals": 2},
    "SGD": {"symbol": "S$", "decimals": 2},
    "BRL": {"symbol": "R$", "decimals": 2},
    "MXN": {"symbol": "MX$", "decimals": 2},
    "ARS": {"symbol": "$", "decimals": 2},
    "RUB": {"symbol": "₽", "decimals": 2},
    "TRY": {"symbol": "₺", "decimals": 2},
    "PLN": {"symbol": "zł", "decimals": 2},
    "CZK": {"symbol": "Kč", "decimals": 2},
    "HUF": {"symbol": "Ft", "decimals": 0},
    "RON": {"symbol": "lei", "decimals": 2},
    "SAR": {"symbol": "﷼", "decimals": 2},
    "AED": {"symbol": "د.إ", "decimals": 2},
    "THB": {"symbol": "฿", "decimals": 2},
    "IDR": {"symbol": "Rp", "decimals": 0},
    "MYR": {"symbol": "RM", "decimals": 2},
    "PHP": {"symbol": "₱", "decimals": 2},
    "TWD": {"symbol": "NT$", "decimals": 0},
    "PKR": {"symbol": "₨", "decimals": 2},
    "BDT": {"symbol": "৳", "decimals": 2},
    "EGP": {"symbol": "E£", "decimals": 2},
    "NGN": {"symbol": "₦", "decimals": 2},
    "ZAR": {"symbol": "R", "decimals": 2},
}

# Date format patterns by locale (strftime)
_DATE_FORMATS = {
    "en-US": {"short": "%m/%d/%Y", "medium": "%b %d, %Y", "long": "%B %d, %Y"},
    "en-GB": {"short": "%d/%m/%Y", "medium": "%d %b %Y", "long": "%d %B %Y"},
    "en-CA": {"short": "%Y-%m-%d", "medium": "%b %d, %Y", "long": "%B %d, %Y"},
    "de-DE": {"short": "%d.%m.%Y", "medium": "%d. %b %Y", "long": "%d. %B %Y"},
    "fr-FR": {"short": "%d/%m/%Y", "medium": "%d %b %Y", "long": "%d %B %Y"},
    "es-ES": {"short": "%d/%m/%Y", "medium": "%d de %b de %Y", "long": "%d de %B de %Y"},
    "pt-BR": {"short": "%d/%m/%Y", "medium": "%d de %b de %Y", "long": "%d de %B de %Y"},
    "ja-JP": {"short": "%Y/%m/%d", "medium": "%Y年%m月%d日", "long": "%Y年%m月%d日"},
    "zh-CN": {"short": "%Y/%m/%d", "medium": "%Y年%m月%d日", "long": "%Y年%m月%d日"},
    "ko-KR": {"short": "%Y. %m. %d.", "medium": "%Y년 %m월 %d일", "long": "%Y년 %m월 %d일"},
    "en-IN": {"short": "%d/%m/%Y", "medium": "%d %b %Y", "long": "%d %B %Y"},
    "ru-RU": {"short": "%d.%m.%Y", "medium": "%d %b %Y г.", "long": "%d %B %Y г."},
    "ar-SA": {"short": "%d/%m/%Y", "medium": "%d %b %Y", "long": "%d %B %Y"},
    "default": {"short": "%Y-%m-%d", "medium": "%d %b %Y", "long": "%d %B %Y"},
}


def _get_locale_config(locale: str) -> dict:
    """Get locale config with fallback to language code then default."""
    if locale in _LOCALE_CONFIG:
        return _LOCALE_CONFIG[locale]
    lang = locale.split("-")[0] if "-" in locale else locale
    for key in _LOCALE_CONFIG:
        if key.startswith(lang + "-"):
            return _LOCALE_CONFIG[key]
    return _LOCALE_CONFIG["default"]


def _get_date_format(locale: str, style: str = "medium") -> str:
    """Get date format string for locale and style."""
    formats = _DATE_FORMATS.get(locale) or _DATE_FORMATS.get(
        locale.split("-")[0] + "-" + locale.split("-")[1] if "-" in locale else "x",
        _DATE_FORMATS["default"]
    )
    return formats.get(style, formats.get("medium", "%d %b %Y"))


def format_number(value: float, locale: str = "en-US", decimals: int = 2) -> str:
    """Format a number with locale-specific separators."""
    cfg = _get_locale_config(locale)
    if math.isnan(value) or math.isinf(value):
        return "—"
    # Round to requested decimals
    factor = 10 ** decimals
    rounded = round(value * factor) / factor
    integer_part = int(abs(rounded))
    decimal_part = abs(rounded) - integer_part
    sign = "-" if rounded < 0 else ""
    # Format integer part with thousands separator
    int_str = str(integer_part)
    if len(int_str) > 3:
        groups = []
        while len(int_str) > 3:
            groups.insert(0, int_str[-3:])
            int_str = int_str[:-3]
        groups.insert(0, int_str)
        int_str = cfg["thousands"].join(groups)
    # Format decimal part
    if decimals > 0:
        dec_str = f"{decimal_part:.{decimals}f}"[1:]  # strip leading 0
        return f"{sign}{int_str}{cfg['decimal']}{dec_str[1:]}"
    return f"{sign}{int_str}"


def format_currency(
    amount: float,
    currency_code: str,
    locale: str = "en-US",
    show_code: bool = False,
) -> str:
    """
    Format a monetary amount with locale-specific currency formatting.

    Args:
        amount: The monetary amount.
        currency_code: ISO 4217 currency code (e.g. "USD", "EUR", "INR").
        locale: BCP 47 locale string (e.g. "en-US", "de-DE", "ja-JP").
        show_code: If True, append the currency code after the symbol.

    Returns:
        Formatted currency string (e.g. "$1,234.56", "1.234,56 €").
    """
    meta = _CURRENCY_META.get(currency_code.upper(), {"symbol": currency_code, "decimals": 2})
    cfg = _get_locale_config(locale)
    symbol = meta["symbol"]
    decimals = meta["decimals"]
    number = format_number(amount, locale=locale, decimals=decimals)
    code_suffix = f" {currency_code}" if show_code else ""
    if cfg["symbol_before"]:
        return f"{symbol}{number}{code_suffix}"
    return f"{number} {symbol}{code_suffix}"


def format_date(d, locale: str = "en-US", style: str = "medium") -> str:
    """
    Format a date with locale-specific formatting.

    Args:
        d: datetime.date or datetime.datetime object.
        locale: BCP 47 locale string.
        style: "short", "medium", "long", or "iso".

    Returns:
        Formatted date string.
    """
    if d is None:
        return ""
    if style == "iso":
        return d.strftime("%Y-%m-%d")
    fmt = _get_date_format(locale, style)
    return d.strftime(fmt)


def get_supported_locales() -> list:
    """Return list of all supported locale codes."""
    return sorted(_LOCALE_CONFIG.keys())


def get_supported_currencies() -> list:
    """Return list of supported currency codes."""
    return sorted(_CURRENCY_META.keys())