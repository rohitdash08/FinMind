"""Locale-aware formatting helpers for dates, currency and numbers."""

import locale as _locale
import threading
from datetime import date, datetime
from decimal import Decimal

# Map BCP-47 locale tags to POSIX locale names (best-effort).
_LOCALE_MAP = {
    "en-US": "en_US.UTF-8",
    "en-IN": "en_IN.UTF-8",
    "en-GB": "en_GB.UTF-8",
    "en-AU": "en_AU.UTF-8",
    "en-CA": "en_CA.UTF-8",
    "en-SG": "en_SG.UTF-8",
    "de-DE": "de_DE.UTF-8",
    "fr-FR": "fr_FR.UTF-8",
    "ja-JP": "ja_JP.UTF-8",
    "ar-AE": "ar_AE.UTF-8",
}

# Currency symbols lookup (fallback when locale formatting unavailable)
_CURRENCY_SYMBOLS = {
    "USD": "$",
    "INR": "₹",
    "EUR": "€",
    "GBP": "£",
    "AED": "د.إ",
    "SGD": "S$",
    "AUD": "A$",
    "CAD": "C$",
    "JPY": "¥",
}

_lock = threading.Lock()


def format_currency(amount, currency_code="INR", user_locale="en-IN"):
    """Format a monetary amount with locale-aware separators and currency symbol."""
    amt = float(amount or 0)
    symbol = _CURRENCY_SYMBOLS.get(currency_code, currency_code)
    posix_locale = _LOCALE_MAP.get(user_locale)

    if posix_locale:
        try:
            with _lock:
                old = _locale.getlocale(_locale.LC_ALL)
                try:
                    _locale.setlocale(_locale.LC_ALL, posix_locale)
                    formatted = _locale.format_string("%.2f", amt, grouping=True)
                finally:
                    _locale.setlocale(_locale.LC_ALL, old)
            return f"{symbol}{formatted}"
        except (_locale.Error, ValueError):
            pass

    # Fallback: simple formatting
    formatted = f"{amt:,.2f}"
    return f"{symbol}{formatted}"


def format_date(d, user_locale="en-IN", fmt=None):
    """Format a date/datetime with locale-aware conventions."""
    if d is None:
        return ""
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d)
        except ValueError:
            return d

    posix_locale = _LOCALE_MAP.get(user_locale)
    date_fmt = fmt or _date_format_for_locale(user_locale)

    if posix_locale:
        try:
            with _lock:
                old = _locale.getlocale(_locale.LC_ALL)
                try:
                    _locale.setlocale(_locale.LC_ALL, posix_locale)
                    return d.strftime(date_fmt)
                finally:
                    _locale.setlocale(_locale.LC_ALL, old)
        except (_locale.Error, ValueError):
            pass

    return d.strftime(date_fmt)


def format_number(n, user_locale="en-IN", decimals=2):
    """Format a number with locale-aware grouping."""
    val = float(n or 0)
    posix_locale = _LOCALE_MAP.get(user_locale)

    if posix_locale:
        try:
            with _lock:
                old = _locale.getlocale(_locale.LC_ALL)
                try:
                    _locale.setlocale(_locale.LC_ALL, posix_locale)
                    fmt_str = f"%.{decimals}f"
                    return _locale.format_string(fmt_str, val, grouping=True)
                finally:
                    _locale.setlocale(_locale.LC_ALL, old)
        except (_locale.Error, ValueError):
            pass

    return f"{val:,.{decimals}f}"


def _date_format_for_locale(user_locale):
    """Return a strftime format string appropriate for the locale."""
    formats = {
        "en-US": "%m/%d/%Y",
        "en-IN": "%d/%m/%Y",
        "en-GB": "%d/%m/%Y",
        "en-AU": "%d/%m/%Y",
        "en-CA": "%Y-%m-%d",
        "en-SG": "%d/%m/%Y",
        "de-DE": "%d.%m.%Y",
        "fr-FR": "%d/%m/%Y",
        "ja-JP": "%Y/%m/%d",
        "ar-AE": "%d/%m/%Y",
    }
    return formats.get(user_locale, "%Y-%m-%d")
