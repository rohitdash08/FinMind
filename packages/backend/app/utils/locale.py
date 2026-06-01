
"""
Locale-aware date, currency, and number formatting for FinMind.
"""
from babel import numbers, dates
from typing import Optional


LOCALE_MAP = {
    "IN": "en_IN",
    "US": "en_US",
    "GB": "en_GB",
    "EU": "de_DE",
    "JP": "ja_JP",
    "CN": "zh_CN",
}


def format_currency(amount: float, currency: str = "INR", locale: str = "en_IN") -> str:
    """Format currency amount with locale-specific formatting."""
    return numbers.format_currency(amount, currency, locale=locale)


def format_number(value: float, locale: str = "en_IN", decimal_places: int = 2) -> str:
    """Format number with locale-specific thousand separators."""
    return numbers.format_decimal(value, locale=locale, format=f"#,##0.{'0' * decimal_places}")


def format_date(date, locale: str = "en_IN", format: str = "medium") -> str:
    """Format date with locale-specific formatting."""
    return dates.format_date(date, locale=locale, format=format)


def format_percentage(value: float, locale: str = "en_IN") -> str:
    """Format percentage with locale-specific formatting."""
    return numbers.format_percent(value / 100, locale=locale)
