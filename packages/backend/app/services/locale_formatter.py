"""
locale_formatter.py — Locale-aware formatting for dates, numbers, and currencies.

Uses Babel for locale-specific output. Falls back to plain ISO / plain float
if the requested locale is unknown or Babel is unavailable.

Public API:
    format_currency(amount, currency_code, locale) -> str
    format_number(value, locale, decimal_places) -> str
    format_date(d, locale, format) -> str
    format_datetime(dt, locale, format) -> str
    supported_locales() -> list[str]
    locale_meta(locale) -> dict
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Union

logger = logging.getLogger("finmind.locale")

# ── Babel import (optional — graceful degradation if not installed) ────────────
try:
    from babel import Locale, UnknownLocaleError
    from babel.dates import format_date as babel_format_date
    from babel.dates import format_datetime as babel_format_datetime
    from babel.numbers import format_currency as babel_format_currency
    from babel.numbers import format_decimal as babel_format_decimal
    _BABEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BABEL_AVAILABLE = False
    logger.warning("Babel not installed — locale formatting will fall back to plain output")

# ── Supported locales (curated list matching FinMind's user base) ─────────────
SUPPORTED_LOCALES: list[str] = [
    "en_US", "en_GB", "en_IN", "en_AU", "en_CA",
    "hi_IN", "ta_IN", "te_IN", "kn_IN", "mr_IN",
    "de_DE", "fr_FR", "es_ES", "es_MX", "pt_BR",
    "ja_JP", "zh_CN", "zh_TW", "ko_KR",
    "ar_SA", "ar_AE",
]

_DEFAULT_LOCALE = "en_IN"  # FinMind default (INR-centric)


def _resolve_locale(locale: str | None) -> str:
    """Normalise locale string; return default if unrecognised."""
    if not locale:
        return _DEFAULT_LOCALE
    # Accept both en-IN and en_IN forms
    normalised = locale.replace("-", "_")
    if normalised in SUPPORTED_LOCALES:
        return normalised
    # Try just the language part
    lang = normalised.split("_")[0]
    for sl in SUPPORTED_LOCALES:
        if sl.startswith(lang + "_"):
            return sl
    logger.debug("Unknown locale '%s', falling back to %s", locale, _DEFAULT_LOCALE)
    return _DEFAULT_LOCALE


def format_currency(
    amount: Union[float, Decimal, int],
    currency_code: str = "INR",
    locale: str | None = None,
) -> str:
    """
    Format an amount as a locale-aware currency string.

    Examples:
        format_currency(1234.5, "INR", "en_IN")  -> "₹1,234.50"
        format_currency(1234.5, "USD", "en_US")  -> "$1,234.50"
        format_currency(1234.5, "EUR", "de_DE")  -> "1.234,50 €"
    """
    loc = _resolve_locale(locale)
    if not _BABEL_AVAILABLE:
        return f"{currency_code} {float(amount):.2f}"
    try:
        return babel_format_currency(float(amount), currency_code.upper(), locale=loc)
    except Exception as exc:
        logger.warning("format_currency failed (locale=%s): %s", loc, exc)
        return f"{currency_code} {float(amount):.2f}"


def format_number(
    value: Union[float, Decimal, int],
    locale: str | None = None,
    decimal_places: int = 2,
) -> str:
    """
    Format a number with locale-appropriate grouping and decimal separators.

    Examples:
        format_number(1234567.89, "en_US") -> "1,234,567.89"
        format_number(1234567.89, "de_DE") -> "1.234.567,89"
        format_number(1234567.89, "en_IN") -> "12,34,567.89"
    """
    loc = _resolve_locale(locale)
    if not _BABEL_AVAILABLE:
        return f"{float(value):.{decimal_places}f}"
    fmt = f"#,##0.{'0' * decimal_places}" if decimal_places > 0 else "#,##0"
    try:
        return babel_format_decimal(float(value), format=fmt, locale=loc)
    except Exception as exc:
        logger.warning("format_number failed (locale=%s): %s", loc, exc)
        return f"{float(value):.{decimal_places}f}"


def format_date(
    d: Union[date, str],
    locale: str | None = None,
    fmt: str = "medium",
) -> str:
    """
    Format a date in a locale-aware style.

    fmt: 'full' | 'long' | 'medium' | 'short'

    Examples:
        format_date(date(2026, 2, 24), "en_US", "medium") -> "Feb 24, 2026"
        format_date(date(2026, 2, 24), "de_DE", "medium") -> "24.02.2026"
        format_date(date(2026, 2, 24), "en_IN", "long")   -> "24 February 2026"
    """
    loc = _resolve_locale(locale)
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d  # return as-is if unparseable
    if not _BABEL_AVAILABLE:
        return d.isoformat()
    try:
        return babel_format_date(d, format=fmt, locale=loc)
    except Exception as exc:
        logger.warning("format_date failed (locale=%s): %s", loc, exc)
        return d.isoformat()


def format_datetime(
    dt: Union[datetime, str],
    locale: str | None = None,
    fmt: str = "medium",
) -> str:
    """Format a datetime in a locale-aware style."""
    loc = _resolve_locale(locale)
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return dt
    if not _BABEL_AVAILABLE:
        return dt.isoformat()
    try:
        return babel_format_datetime(dt, format=fmt, locale=loc)
    except Exception as exc:
        logger.warning("format_datetime failed (locale=%s): %s", loc, exc)
        return dt.isoformat()


def supported_locales() -> list[str]:
    """Return the list of supported locale codes."""
    return list(SUPPORTED_LOCALES)


def locale_meta(locale: str | None = None) -> dict:
    """
    Return metadata about a locale: display name, currency, date/number format examples.
    """
    loc = _resolve_locale(locale)
    meta: dict = {"locale": loc, "babel_available": _BABEL_AVAILABLE}
    if _BABEL_AVAILABLE:
        try:
            bl = Locale.parse(loc)
            meta["display_name"] = bl.get_display_name("en")
            meta["language"] = bl.language_name
            meta["territory"] = bl.territory_name
            meta["currency"] = str(bl.currency_symbols.get(loc, ""))
            meta["decimal_symbol"] = bl.number_symbols.get("decimal", ".")
            meta["grouping_symbol"] = bl.number_symbols.get("group", ",")
        except Exception:
            pass
    return meta
