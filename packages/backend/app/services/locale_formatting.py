"""
Locale-aware date, currency & number formatting service for FinMind.

Uses Babel for i18n formatting with locale auto-detection from the
user's preferred_currency setting. Provides formatting for:
- Currency amounts (symbol, position, decimals)
- Numbers (thousands separator, decimal separator)
- Percentages
- Dates (short, medium, long, full)
- Relative time strings

Supports 15+ locales out of the box.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any

from babel import Locale
from babel.core import UnknownLocaleError
from babel.dates import format_date, format_datetime, format_time
from babel.numbers import (
    format_currency,
    format_decimal,
    format_percent,
)
from decimal import Decimal

logger = logging.getLogger("finmind")

# ── Currency → locale mapping ──────────────────────────────────────────
# Maps currency codes to the most common locale for that currency.
# Users can override by passing an explicit locale.
CURRENCY_LOCALE_MAP: dict[str, str] = {
    "INR": "en_IN",
    "USD": "en_US",
    "EUR": "de_DE",
    "GBP": "en_GB",
    "JPY": "ja_JP",
    "CNY": "zh_CN",
    "KRW": "ko_KR",
    "BRL": "pt_BR",
    "CAD": "en_CA",
    "AUD": "en_AU",
    "CHF": "de_CH",
    "MXN": "es_MX",
    "SGD": "en_SG",
    "HKD": "zh_HK",
    "SEK": "sv_SE",
    "NOK": "nb_NO",
    "DKK": "da_DK",
    "NZD": "en_NZ",
    "ZAR": "en_ZA",
    "RUB": "ru_RU",
    "TRY": "tr_TR",
    "PLN": "pl_PL",
    "THB": "th_TH",
    "AED": "ar_AE",
    "SAR": "ar_SA",
}

# Supported locales with display names
SUPPORTED_LOCALES: dict[str, str] = {
    "en_US": "English (United States)",
    "en_IN": "English (India)",
    "en_GB": "English (United Kingdom)",
    "en_AU": "English (Australia)",
    "en_CA": "English (Canada)",
    "en_NZ": "English (New Zealand)",
    "en_SG": "English (Singapore)",
    "en_ZA": "English (South Africa)",
    "de_DE": "German (Germany)",
    "de_CH": "German (Switzerland)",
    "fr_FR": "French (France)",
    "es_MX": "Spanish (Mexico)",
    "pt_BR": "Portuguese (Brazil)",
    "ja_JP": "Japanese (Japan)",
    "zh_CN": "Chinese (China)",
    "zh_HK": "Chinese (Hong Kong)",
    "ko_KR": "Korean (South Korea)",
    "sv_SE": "Swedish (Sweden)",
    "nb_NO": "Norwegian Bokmål (Norway)",
    "da_DK": "Danish (Denmark)",
    "ru_RU": "Russian (Russia)",
    "tr_TR": "Turkish (Turkey)",
    "pl_PL": "Polish (Poland)",
    "th_TH": "Thai (Thailand)",
    "ar_AE": "Arabic (UAE)",
    "ar_SA": "Arabic (Saudi Arabia)",
}


def resolve_locale(currency: str, explicit_locale: str | None = None) -> str:
    """Resolve a Babel locale string from currency code + optional override.

    Priority:
    1. Explicit locale (if provided and valid)
    2. Currency → locale mapping
    3. Fallback to en_US
    """
    if explicit_locale:
        try:
            Locale.parse(explicit_locale)
            return explicit_locale
        except (UnknownLocaleError, ValueError):
            logger.warning("Unknown locale %r, falling back to currency mapping", explicit_locale)

    locale = CURRENCY_LOCALE_MAP.get(currency.upper())
    if locale:
        return locale

    logger.debug("No locale mapping for currency %r, defaulting to en_US", currency)
    return "en_US"


def format_currency_amount(
    amount: float | Decimal | int,
    currency: str = "USD",
    locale: str | None = None,
    format_type: str | None = None,
) -> str:
    """Format a currency amount with locale-aware symbol, position, and decimals.

    Args:
        amount: The numeric amount.
        currency: ISO 4217 currency code (e.g. 'USD', 'INR', 'EUR').
        locale: Babel locale string (e.g. 'en_US'). Auto-detected from currency if None.
        format_type: Babel currency format — None (standard), 'short', or 'name'.

    Returns:
        Formatted currency string, e.g. '$1,234.56' or '₹1,23,456.78'.
    """
    resolved = resolve_locale(currency, locale)
    try:
        return format_currency(
            Decimal(str(amount)),
            currency.upper(),
            locale=resolved,
            format=format_type,
        )
    except Exception:
        # Fallback: basic formatting if Babel fails
        return f"{currency.upper()} {amount:,.2f}"


def format_number(
    value: float | Decimal | int,
    locale: str | None = None,
    currency: str | None = None,
) -> str:
    """Format a number with locale-aware separators.

    Args:
        value: The numeric value.
        locale: Babel locale string. Auto-detected from currency if None.
        currency: Optional currency code for locale resolution.

    Returns:
        Formatted number string, e.g. '1,234.56' or '1.234,56'.
    """
    if locale is None and currency:
        locale = resolve_locale(currency)
    resolved = locale or "en_US"
    try:
        return format_decimal(Decimal(str(value)), locale=resolved)
    except Exception:
        return f"{value:,.2f}"


def format_percentage(
    value: float | Decimal | int,
    locale: str | None = None,
    currency: str | None = None,
) -> str:
    """Format a percentage with locale-aware separators.

    Args:
        value: The percentage value (e.g. 0.1523 for 15.23%).
        locale: Babel locale string. Auto-detected from currency if None.
        currency: Optional currency code for locale resolution.

    Returns:
        Formatted percentage string, e.g. '15.23%' or '15,23 %'.
    """
    if locale is None and currency:
        locale = resolve_locale(currency)
    resolved = locale or "en_US"
    try:
        return format_percent(Decimal(str(value)), locale=resolved)
    except Exception:
        return f"{value * 100:.2f}%"


def format_date_locale(
    value: date | datetime,
    format_type: str = "medium",
    locale: str | None = None,
    currency: str | None = None,
) -> str:
    """Format a date with locale-aware patterns.

    Args:
        value: The date or datetime to format.
        format_type: 'short', 'medium', 'long', or 'full'.
        locale: Babel locale string. Auto-detected from currency if None.
        currency: Optional currency code for locale resolution.

    Returns:
        Formatted date string, e.g. 'Feb 16, 2026' or '16.02.2026'.
    """
    if locale is None and currency:
        locale = resolve_locale(currency)
    resolved = locale or "en_US"
    try:
        if isinstance(value, datetime):
            return format_datetime(value, format=format_type, locale=resolved)
        return format_date(value, format=format_type, locale=resolved)
    except Exception:
        return str(value)


def format_time_locale(
    value: datetime,
    format_type: str = "medium",
    locale: str | None = None,
    currency: str | None = None,
) -> str:
    """Format a time with locale-aware patterns.

    Args:
        value: The datetime to extract time from.
        format_type: 'short', 'medium', 'long', or 'full'.
        locale: Babel locale string. Auto-detected from currency if None.
        currency: Optional currency code for locale resolution.

    Returns:
        Formatted time string, e.g. '3:45 PM' or '15:45:00'.
    """
    if locale is None and currency:
        locale = resolve_locale(currency)
    resolved = locale or "en_US"
    try:
        return format_time(value, format=format_type, locale=resolved)
    except Exception:
        return str(value)


def format_relative_time(
    value: date | datetime,
    reference: date | datetime | None = None,
) -> str:
    """Generate a human-readable relative time string.

    Args:
        value: The target date/datetime.
        reference: The reference point (defaults to today in local timezone).

    Returns:
        Relative time string like '2 days ago', 'in 3 weeks', 'today'.
    """
    if reference is None:
        reference = date.today()

    # Normalize both to date objects for comparison
    if isinstance(value, datetime):
        target = value.date()
    else:
        target = value

    if isinstance(reference, datetime):
        ref = reference.date()
    else:
        ref = reference

    delta = target - ref
    days = delta.days

    if days == 0:
        return "today"
    if days == 1:
        return "tomorrow"
    if days == -1:
        return "yesterday"
    if days > 1:
        if days < 7:
            return f"in {days} days"
        if days < 30:
            weeks = days // 7
            return f"in {weeks} week{'s' if weeks > 1 else ''}"
        if days < 365:
            months = days // 30
            return f"in {months} month{'s' if months > 1 else ''}"
        years = days // 365
        return f"in {years} year{'s' if years > 1 else ''}"
    # Negative days = past
    abs_days = abs(days)
    if abs_days < 7:
        return f"{abs_days} day{'s' if abs_days > 1 else ''} ago"
    if abs_days < 30:
        weeks = abs_days // 7
        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
    if abs_days < 365:
        months = abs_days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    years = abs_days // 365
    return f"{years} year{'s' if years > 1 else ''} ago"


def get_locale_info(locale: str) -> dict[str, Any]:
    """Get detailed locale information for display.

    Returns:
        Dict with locale metadata: display_name, currency, date_format, number_format.
    """
    try:
        loc = Locale.parse(locale)
    except (UnknownLocaleError, ValueError):
        return {"locale": locale, "error": "unknown locale"}

    return {
        "locale": locale,
        "display_name": loc.display_name,
        "language": loc.language_name,
        "territory": loc.territory_name or None,
        "currency_symbols": dict(loc.currency_symbols) if loc.currency_symbols else {},
        "number_format": {
            "decimal_separator": loc.number_symbols.get("decimal", "."),
            "group_separator": loc.number_symbols.get("group", ","),
        },
    }
