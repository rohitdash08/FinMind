"""Locale-aware formatting service for dates, currencies, and numbers."""

import locale
from datetime import datetime, date
from typing import Optional, Union
from babel import numbers as babel_numbers, dates as babel_dates


# Supported locales with their currency codes
LOCALE_CURRENCY_MAP = {
    "en_US": "USD",
    "en_GB": "GBP",
    "en_AU": "AUD",
    "en_CA": "CAD",
    "de_DE": "EUR",
    "fr_FR": "EUR",
    "ja_JP": "JPY",
    "zh_CN": "CNY",
    "zh_TW": "TWD",
    "ko_KR": "KRW",
    "pt_BR": "BRL",
    "es_ES": "EUR",
    "es_MX": "MXN",
    "hi_IN": "INR",
    "ru_RU": "RUB",
}

DEFAULT_LOCALE = "en_US"
DEFAULT_CURRENCY = "USD"


def format_currency(
    amount: Union[int, float],
    currency: Optional[str] = None,
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a number as currency with locale-aware symbols and separators.

    Args:
        amount: The monetary amount to format.
        currency: ISO 4217 currency code (e.g. 'USD'). Auto-detected from locale if None.
        locale_str: Locale string (e.g. 'en_US', 'zh_CN').

    Returns:
        Formatted currency string (e.g. '$1,234.56', '¥1,234').
    """
    if currency is None:
        currency = LOCALE_CURRENCY_MAP.get(locale_str, DEFAULT_CURRENCY)
    return babel_numbers.format_currency(amount, currency, locale=locale_str)


def format_number(
    value: Union[int, float],
    decimal_places: Optional[int] = None,
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a number with locale-aware grouping and decimal separators.

    Args:
        value: The number to format.
        decimal_places: Fixed decimal places. None for auto.
        locale_str: Locale string.

    Returns:
        Formatted number string (e.g. '1,234.56' or '1.234,56').
    """
    if decimal_places is not None:
        return babel_numbers.format_decimal(
            value, format=f"#,##0.{'0' * decimal_places}", locale=locale_str
        )
    return babel_numbers.format_decimal(value, locale=locale_str)


def format_percent(
    value: Union[int, float],
    decimal_places: int = 1,
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a number as a percentage.

    Args:
        value: The value (0.15 = 15%).
        decimal_places: Number of decimal places.
        locale_str: Locale string.

    Returns:
        Formatted percentage string (e.g. '15.0%').
    """
    return babel_numbers.format_percent(
        value, format=f"#,##0.{'0' * decimal_places}%", locale=locale_str
    )


def format_date(
    dt: Union[datetime, date],
    format: str = "medium",
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a date with locale-aware patterns.

    Args:
        dt: Date or datetime object.
        format: One of 'short', 'medium', 'long', 'full'.
        locale_str: Locale string.

    Returns:
        Formatted date string.
    """
    return babel_dates.format_date(dt, format=format, locale=locale_str)


def format_datetime(
    dt: datetime,
    format: str = "medium",
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a datetime with locale-aware patterns.

    Args:
        dt: Datetime object.
        format: One of 'short', 'medium', 'long', 'full'.
        locale_str: Locale string.

    Returns:
        Formatted datetime string.
    """
    return babel_dates.format_datetime(dt, format=format, locale=locale_str)


def format_relative_time(
    dt: datetime,
    now: Optional[datetime] = None,
    locale_str: str = DEFAULT_LOCALE,
) -> str:
    """Format a datetime as relative time (e.g. '3 days ago').

    Args:
        dt: The target datetime.
        now: Reference time. Defaults to utcnow.
        locale_str: Locale string.

    Returns:
        Relative time string.
    """
    if now is None:
        now = datetime.utcnow()
    delta = now - dt
    return babel_dates.format_timedelta(-delta, locale=locale_str, add_direction=True)


def get_supported_locales() -> list:
    """Return list of supported locale strings."""
    return sorted(LOCALE_CURRENCY_MAP.keys())


def get_currency_for_locale(locale_str: str) -> str:
    """Get the default currency code for a locale."""
    return LOCALE_CURRENCY_MAP.get(locale_str, DEFAULT_CURRENCY)
