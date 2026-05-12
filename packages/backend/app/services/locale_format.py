"""Locale-aware date, currency & number formatting utilities."""

from decimal import Decimal
from datetime import date, datetime

# Currency formatting rules
CURRENCY_FORMATS = {
    "USD": {"symbol": "$", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
    "EUR": {"symbol": "€", "position": "after", "decimal": ",", "thousands": ".", "decimals": 2},
    "GBP": {"symbol": "£", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
    "INR": {"symbol": "₹", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
    "JPY": {"symbol": "¥", "position": "before", "decimal": ".", "thousands": ",", "decimals": 0},
    "AED": {"symbol": "د.إ", "position": "after", "decimal": ".", "thousands": ",", "decimals": 2},
    "SGD": {"symbol": "S$", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
    "AUD": {"symbol": "A$", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
    "CAD": {"symbol": "C$", "position": "before", "decimal": ".", "thousands": ",", "decimals": 2},
}

# Date format by locale
DATE_FORMATS = {
    "en-US": "%m/%d/%Y",
    "en-GB": "%d/%m/%Y",
    "de-DE": "%d.%m.%Y",
    "ja-JP": "%Y年%m月%d日",
    "hi-IN": "%d/%m/%Y",
    "default": "%Y-%m-%d",
}


def format_currency(amount: float | Decimal, currency: str = "INR") -> str:
    """Format amount according to currency rules."""
    fmt = CURRENCY_FORMATS.get(currency, CURRENCY_FORMATS["USD"])
    decimals = fmt["decimals"]
    abs_amount = abs(float(amount))

    # Format number
    if decimals > 0:
        integer_part = int(abs_amount)
        decimal_part = round(abs_amount - integer_part, decimals)
        dec_str = str(decimal_part)[2:].ljust(decimals, "0")[:decimals]
    else:
        integer_part = round(abs_amount)
        dec_str = ""

    # Add thousands separator
    int_str = ""
    digits = str(integer_part)
    for i, d in enumerate(reversed(digits)):
        if i > 0 and i % 3 == 0:
            int_str = fmt["thousands"] + int_str
        int_str = d + int_str

    number_str = f"{int_str}{fmt['decimal']}{dec_str}" if dec_str else int_str
    sign = "-" if float(amount) < 0 else ""

    if fmt["position"] == "before":
        return f"{sign}{fmt['symbol']}{number_str}"
    return f"{sign}{number_str} {fmt['symbol']}"


def format_date(d: date | datetime, locale: str = "default") -> str:
    """Format date according to locale."""
    fmt = DATE_FORMATS.get(locale, DATE_FORMATS["default"])
    return d.strftime(fmt)


def format_number(value: float, decimals: int = 2, locale: str = "en-US") -> str:
    """Format number with locale-appropriate separators."""
    if locale in ("de-DE",):
        thousands, decimal = ".", ","
    else:
        thousands, decimal = ",", "."

    formatted = f"{abs(value):,.{decimals}f}"
    if thousands != ",":
        formatted = formatted.replace(",", "TEMP").replace(".", decimal).replace("TEMP", thousands)

    return f"-{formatted}" if value < 0 else formatted
