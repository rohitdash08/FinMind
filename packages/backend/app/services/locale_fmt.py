"""
Locale-aware date, currency & number formatting (Issue #131).

Uses Python's built-in locale + babel (if available) for formatting.
Falls back to a simple pure-Python formatter when babel is not installed.

Supported formats:
- format_currency(amount, currency, locale) → "₹1,23,456.78" / "$1,234.56" / "1.234,56 €"
- format_number(number, locale)             → "1,23,456" / "1,234,567"
- format_date(dt, locale, fmt)             → "14 Mar 2026" / "03/14/2026"
- format_datetime(dt, locale, fmt)         → "14 Mar 2026, 10:30 AM"
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger("finmind.locale_fmt")

# ── Locale metadata (currency symbol, decimal/thousands separators) ──────────

_LOCALE_META: dict[str, dict] = {
    # locale_code: {decimal_sep, thousands_sep, date_fmt, currency_position,
    #               lakh_grouping (bool), time_fmt ("%I:%M %p" 12h or "%H:%M" 24h)}
    "en_US": {"decimal": ".", "thousands": ",", "date": "%m/%d/%Y", "pos": "prefix", "lakh": False, "time": "%I:%M %p"},
    "en_GB": {"decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "pos": "prefix", "lakh": False, "time": "%I:%M %p"},
    # en_IN and hi_IN use the South-Asian lakh grouping system:
    #   3 digits from the right, then groups of 2 → 1,23,45,678
    # They also conventionally use 12-hour time with AM/PM.
    "en_IN": {"decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "pos": "prefix", "lakh": True,  "time": "%I:%M %p"},
    "hi_IN": {"decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "pos": "prefix", "lakh": True,  "time": "%I:%M %p"},
    "en_AU": {"decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "pos": "prefix", "lakh": False, "time": "%I:%M %p"},
    "de_DE": {"decimal": ",", "thousands": ".", "date": "%d.%m.%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
    "fr_FR": {"decimal": ",", "thousands": "\u202f", "date": "%d/%m/%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
    "it_IT": {"decimal": ",", "thousands": ".", "date": "%d/%m/%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
    "es_ES": {"decimal": ",", "thousands": ".", "date": "%d/%m/%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
    "pt_BR": {"decimal": ",", "thousands": ".", "date": "%d/%m/%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
    "ja_JP": {"decimal": ".", "thousands": ",", "date": "%Y/%m/%d", "pos": "prefix", "lakh": False, "time": "%H:%M"},
    "zh_CN": {"decimal": ".", "thousands": ",", "date": "%Y/%m/%d", "pos": "prefix", "lakh": False, "time": "%H:%M"},
    "ar_SA": {"decimal": ".", "thousands": ",", "date": "%d/%m/%Y", "pos": "suffix", "lakh": False, "time": "%H:%M"},
}

_CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥",
    "INR": "₹", "CNY": "¥", "AED": "د.إ", "SGD": "S$",
    "AUD": "A$", "CAD": "C$", "BRL": "R$", "KRW": "₩",
    "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr",
}

_DEFAULT_LOCALE = "en_IN"


def _get_meta(locale: str) -> dict:
    """Return locale metadata, falling back to en_IN."""
    return _LOCALE_META.get(locale, _LOCALE_META[_DEFAULT_LOCALE])


def _format_number_parts(
    amount: Decimal,
    decimal_sep: str,
    thousands_sep: str,
    decimals: int = 2,
    lakh: bool = False,
) -> str:
    """Format a Decimal with the given separators.

    When ``lakh=True`` the South-Asian lakh grouping is applied:
    the rightmost group is always 3 digits; every subsequent group to the
    left is 2 digits.  Example: 1234567 → "12,34,567".

    Standard grouping (lakh=False): groups of 3 throughout.
    """
    rounded = float(amount)
    if decimals > 0:
        int_part, frac_part = f"{rounded:.{decimals}f}".split(".")
    else:
        int_part = str(int(round(rounded)))
        frac_part = ""

    # Build integer string with appropriate grouping
    if lakh and len(int_part) > 3:
        # First (rightmost) group: 3 digits; subsequent groups: 2 digits each.
        reversed_digits = int_part[::-1]
        groups: list[str] = [reversed_digits[:3]]
        pos = 3
        while pos < len(reversed_digits):
            groups.append(reversed_digits[pos:pos + 2])
            pos += 2
        int_str = thousands_sep.join(g[::-1] for g in reversed(groups))
    else:
        # Standard grouping: 3 digits per group
        int_str = ""
        for i, ch in enumerate(reversed(int_part)):
            if i > 0 and i % 3 == 0:
                int_str = thousands_sep + int_str
            int_str = ch + int_str

    if frac_part:
        return int_str + decimal_sep + frac_part
    return int_str


def format_currency(amount: Any, currency: str, locale: str = _DEFAULT_LOCALE) -> str:
    """
    Format a monetary amount with the correct currency symbol and locale separators.

    Examples:
        format_currency(1234.56, "INR", "en_IN") → "₹1,234.56"
        format_currency(1234.56, "EUR", "de_DE") → "1.234,56 €"
        format_currency(1234.56, "USD", "en_US") → "$1,234.56"
    """
    try:
        amount = Decimal(str(amount))
    except Exception:
        return str(amount)

    meta = _get_meta(locale)
    symbol = _CURRENCY_SYMBOLS.get(currency.upper(), currency.upper())
    formatted = _format_number_parts(amount, meta["decimal"], meta["thousands"], decimals=2, lakh=meta.get("lakh", False))

    if meta["pos"] == "prefix":
        return f"{symbol}{formatted}"
    else:
        return f"{formatted}\u00a0{symbol}"


def format_number(number: Any, locale: str = _DEFAULT_LOCALE, decimals: int = 0) -> str:
    """
    Format a plain number with locale-appropriate thousands separators.

    Examples:
        format_number(1234567, "en_US")  → "1,234,567"
        format_number(1234567, "de_DE")  → "1.234.567"
        format_number(1234.5, "fr_FR", decimals=2) → "1\u202f234,50"
    """
    try:
        number = Decimal(str(number))
    except Exception:
        return str(number)
    meta = _get_meta(locale)
    return _format_number_parts(number, meta["decimal"], meta["thousands"], decimals=decimals, lakh=meta.get("lakh", False))


def format_date(dt: date | str, locale: str = _DEFAULT_LOCALE, style: str = "medium") -> str:
    """
    Format a date according to locale conventions.

    style:
        "short"  → locale-specific short (e.g. 14/03/26)
        "medium" → e.g. 14 Mar 2026
        "long"   → e.g. Saturday, 14 March 2026
        "iso"    → YYYY-MM-DD (always)

    Examples:
        format_date(date(2026,3,14), "en_US") → "03/14/2026"
        format_date(date(2026,3,14), "de_DE") → "14.03.2026"
    """
    if isinstance(dt, str):
        try:
            dt = date.fromisoformat(dt)
        except ValueError:
            return dt

    meta = _get_meta(locale)

    if style == "iso":
        return dt.strftime("%Y-%m-%d")
    if style == "medium":
        return dt.strftime("%d %b %Y")
    if style == "long":
        return dt.strftime("%A, %d %B %Y")
    # short — use locale-specific pattern
    return dt.strftime(meta["date"])


def format_datetime(dt: datetime | str, locale: str = _DEFAULT_LOCALE, style: str = "medium") -> str:
    """Format a datetime with both date and time, locale-aware."""
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt

    meta = _get_meta(locale)
    date_str = format_date(dt.date(), locale, style)
    # Use the locale-appropriate time format: 12-hour (AM/PM) for en_US, en_IN etc.;
    # 24-hour for de_DE, fr_FR, ja_JP, zh_CN and most European/Asian locales.
    time_str = dt.strftime(meta.get("time", "%H:%M"))
    return f"{date_str}, {time_str}"


def get_locale_info(locale: str) -> dict:
    """Return metadata about a locale for client-side use."""
    meta = _get_meta(locale)
    return {
        "locale": locale,
        "decimal_separator": meta["decimal"],
        "thousands_separator": meta["thousands"],
        "date_format": meta["date"],
        "currency_symbol_position": meta["pos"],
        "supported": locale in _LOCALE_META,
    }


SUPPORTED_LOCALES = sorted(_LOCALE_META.keys())
