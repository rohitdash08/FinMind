"""
Locale-aware formatting service for dates, currencies, and numbers.
Supports common locales: en-US, en-GB, de-DE, fr-FR, ja-JP, es-ES, pt-BR, zh-CN.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import re
from datetime import date, datetime


# Locale configuration table
LOCALE_CONFIG = {
    "en-US": {
        "date_format": "%B %d, %Y",
        "short_date": "%m/%d/%Y",
        "thousands_sep": ",",
        "decimal_sep": ".",
        "currency_symbol": "$",
        "currency_position": "before",
        "currency_code": "USD",
        "name": "English (US)",
    },
    "en-GB": {
        "date_format": "%d %B %Y",
        "short_date": "%d/%m/%Y",
        "thousands_sep": ",",
        "decimal_sep": ".",
        "currency_symbol": "£",
        "currency_position": "before",
        "currency_code": "GBP",
        "name": "English (UK)",
    },
    "de-DE": {
        "date_format": "%d. %B %Y",
        "short_date": "%d.%m.%Y",
        "thousands_sep": ".",
        "decimal_sep": ",",
        "currency_symbol": "€",
        "currency_position": "after",
        "currency_code": "EUR",
        "name": "Deutsch (Deutschland)",
    },
    "fr-FR": {
        "date_format": "%d %B %Y",
        "short_date": "%d/%m/%Y",
        "thousands_sep": " ",
        "decimal_sep": ",",
        "currency_symbol": "€",
        "currency_position": "after",
        "currency_code": "EUR",
        "name": "Français (France)",
    },
    "ja-JP": {
        "date_format": "%Y年%m月%d日",
        "short_date": "%Y/%m/%d",
        "thousands_sep": ",",
        "decimal_sep": ".",
        "currency_symbol": "¥",
        "currency_position": "before",
        "currency_code": "JPY",
        "name": "日本語 (日本)",
    },
    "es-ES": {
        "date_format": "%d de %B de %Y",
        "short_date": "%d/%m/%Y",
        "thousands_sep": ".",
        "decimal_sep": ",",
        "currency_symbol": "€",
        "currency_position": "after",
        "currency_code": "EUR",
        "name": "Español (España)",
    },
    "pt-BR": {
        "date_format": "%d de %B de %Y",
        "short_date": "%d/%m/%Y",
        "thousands_sep": ".",
        "decimal_sep": ",",
        "currency_symbol": "R$",
        "currency_position": "before",
        "currency_code": "BRL",
        "name": "Português (Brasil)",
    },
    "zh-CN": {
        "date_format": "%Y年%m月%d日",
        "short_date": "%Y/%m/%d",
        "thousands_sep": ",",
        "decimal_sep": ".",
        "currency_symbol": "¥",
        "currency_position": "before",
        "currency_code": "CNY",
        "name": "中文 (中国)",
    },
}

# Month names for languages that need them (strftime %B uses C locale)
MONTH_NAMES = {
    "de-DE": [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember"
    ],
    "fr-FR": [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
    ],
    "es-ES": [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ],
    "pt-BR": [
        "janeiro", "fevereiro", "março", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
    ],
}


@dataclass
class LocaleFormattingResult:
    locale: str
    locale_name: str
    formatted_date: str
    formatted_date_short: str
    formatted_currency: str
    formatted_number: str
    currency_code: str
    input_date: str
    input_amount: float
    input_number: float


def _get_locale_config(locale: str) -> dict:
    """Get config for locale, falling back to en-US."""
    return LOCALE_CONFIG.get(locale, LOCALE_CONFIG["en-US"])


def _format_number(value: float, thousands_sep: str, decimal_sep: str, decimal_places: int = 2) -> str:
    """Format a number with locale-specific separators."""
    # Format with standard Python first (always uses . for decimal)
    formatted = f"{abs(value):,.{decimal_places}f}"
    # Replace separators
    # Step 1: replace comma thousands sep with placeholder
    formatted = formatted.replace(",", "THOUSANDS")
    # Step 2: replace dot decimal with locale decimal
    formatted = formatted.replace(".", decimal_sep)
    # Step 3: replace placeholder with locale thousands
    formatted = formatted.replace("THOUSANDS", thousands_sep)
    if value < 0:
        formatted = "-" + formatted
    return formatted


def _format_date_localized(d: date, fmt: str, locale: str) -> str:
    """Format date, replacing English month names with locale-specific ones."""
    # First, format with standard strftime (months in English)
    result = d.strftime(fmt)
    # Replace month names if needed
    if locale in MONTH_NAMES:
        en_months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        locale_months = MONTH_NAMES[locale]
        month_idx = d.month - 1
        result = result.replace(en_months[month_idx], locale_months[month_idx])
    return result


def format_for_locale(
    locale: str,
    amount: float,
    number: float,
    date_str: Optional[str] = None,
) -> LocaleFormattingResult:
    """
    Format a date, currency amount, and plain number for the given locale.

    Args:
        locale: BCP 47 locale tag (e.g. "en-US", "de-DE")
        amount: Monetary amount to format
        number: Plain number to format
        date_str: ISO 8601 date string (YYYY-MM-DD). Defaults to today.

    Returns:
        LocaleFormattingResult with all formatted values.
    """
    cfg = _get_locale_config(locale)

    # Parse date
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            d = date.today()
    else:
        d = date.today()

    thousands_sep = cfg["thousands_sep"]
    decimal_sep = cfg["decimal_sep"]
    currency_code = cfg["currency_code"]

    # For JPY and similar currencies, no decimal places
    decimal_places = 0 if currency_code in ("JPY", "CNY") else 2

    # Format date
    formatted_date = _format_date_localized(d, cfg["date_format"], locale)
    formatted_date_short = _format_date_localized(d, cfg["short_date"], locale)

    # Format currency
    amount_str = _format_number(amount, thousands_sep, decimal_sep, decimal_places)
    symbol = cfg["currency_symbol"]
    if cfg["currency_position"] == "before":
        formatted_currency = f"{symbol}{amount_str}"
    else:
        formatted_currency = f"{amount_str} {symbol}"

    # Format plain number (always 2 decimal places)
    formatted_number = _format_number(number, thousands_sep, decimal_sep, 2)

    return LocaleFormattingResult(
        locale=locale,
        locale_name=cfg["name"],
        formatted_date=formatted_date,
        formatted_date_short=formatted_date_short,
        formatted_currency=formatted_currency,
        formatted_number=formatted_number,
        currency_code=currency_code,
        input_date=d.isoformat(),
        input_amount=amount,
        input_number=number,
    )


def list_supported_locales() -> list[dict]:
    """Return list of supported locales with metadata."""
    return [
        {
            "locale": k,
            "name": v["name"],
            "currency_code": v["currency_code"],
            "currency_symbol": v["currency_symbol"],
        }
        for k, v in LOCALE_CONFIG.items()
    ]