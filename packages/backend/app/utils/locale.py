"""
Locale-aware date, currency, and number formatting for FinMind.
"""
from babel import numbers, dates
from typing import Optional
from datetime import date, datetime


LOCALE_MAP = {
    "IN": "en_IN",
    "US": "en_US",
    "GB": "en_GB",
    "EU": "de_DE",
    "JP": "ja_JP",
    "CN": "zh_CN",
}


def format_currency(amount: float, currency: str = "INR", locale: str = "en_IN") -> str:
    """Format currency amount with locale-specific formatting.
    
    Args:
        amount: Amount to format
        currency: Currency code (e.g., "INR", "USD", "EUR")
        locale: Locale string (e.g., "en_IN", "en_US")
        
    Returns:
        Formatted currency string
    """
    return numbers.format_currency(amount, currency, locale=locale)


def format_number(value: float, locale: str = "en_IN", decimal_places: int = 2) -> str:
    """Format number with locale-specific thousand separators.
    
    Args:
        value: Number to format
        locale: Locale string
        decimal_places: Number of decimal places
        
    Returns:
        Formatted number string
    """
    return numbers.format_decimal(value, locale=locale, format=f"#,##0.{'0' * decimal_places}")


def format_date(date_obj, locale: str = "en_IN", format: str = "medium") -> str:
    """Format date with locale-specific formatting.
    
    Args:
        date_obj: Date object (datetime or date)
        locale: Locale string
        format: Format style ("short", "medium", "long", "full")
        
    Returns:
        Formatted date string
    """
    if isinstance(date_obj, datetime):
        date_obj = date_obj.date()
    return dates.format_date(date_obj, locale=locale, format=format)


def format_percentage(value: float, locale: str = "en_IN", is_decimal: bool = False) -> str:
    """Format percentage with locale-specific formatting.
    
    Args:
        value: Percentage value
        locale: Locale string
        is_decimal: If True, value is already in decimal form (e.g., 0.5 for 50%)
                   If False, value is in percentage form (e.g., 50 for 50%)
        
    Returns:
        Formatted percentage string
    """
    if not is_decimal:
        # Convert from percentage form to decimal form
        value = value / 100
    return numbers.format_percent(value, locale=locale)


def get_locale_for_country(country_code: str) -> str:
    """Get locale string for country code.
    
    Args:
        country_code: Two-letter country code (e.g., "IN", "US")
        
    Returns:
        Locale string, defaults to "en_IN" if not found
    """
    return LOCALE_MAP.get(country_code.upper(), "en_IN")
