"""Locale-aware formatting service for dates, currencies, and numbers.

Provides comprehensive locale support including:
- Currency formatting with locale-specific symbols, separators, and placement
- Date formatting with locale-aware patterns and relative dates
- Number formatting with locale-specific grouping and decimal separators
- Timezone conversion and display
- User preference management
"""

from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import re

from app.extensions import db
from app.models import User


# ─── Locale Registry ────────────────────────────────────────────────

LOCALE_CONFIG = {
    "en_US": {
        "name": "English (US)",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "currency_format": "{symbol}{amount}",
        "date_formats": {
            "short": "%m/%d/%Y",
            "medium": "%b %d, %Y",
            "long": "%B %d, %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Today",
            "yesterday": "Yesterday",
            "tomorrow": "Tomorrow",
            "days_ago": "{n} days ago",
            "in_days": "in {n} days",
        },
    },
    "en_GB": {
        "name": "English (UK)",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "currency_format": "{symbol}{amount}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d %B %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Today",
            "yesterday": "Yesterday",
            "tomorrow": "Tomorrow",
            "days_ago": "{n} days ago",
            "in_days": "in {n} days",
        },
    },
    "de_DE": {
        "name": "Deutsch (Germany)",
        "decimal_sep": ",",
        "thousands_sep": ".",
        "currency_format": "{amount} {symbol}",
        "date_formats": {
            "short": "%d.%m.%Y",
            "medium": "%d. %b %Y",
            "long": "%d. %B %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Heute",
            "yesterday": "Gestern",
            "tomorrow": "Morgen",
            "days_ago": "vor {n} Tagen",
            "in_days": "in {n} Tagen",
        },
    },
    "fr_FR": {
        "name": "Français (France)",
        "decimal_sep": ",",
        "thousands_sep": "\u202f",  # narrow no-break space
        "currency_format": "{amount} {symbol}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d %B %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Aujourd'hui",
            "yesterday": "Hier",
            "tomorrow": "Demain",
            "days_ago": "il y a {n} jours",
            "in_days": "dans {n} jours",
        },
    },
    "ja_JP": {
        "name": "日本語 (Japan)",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "currency_format": "{symbol}{amount}",
        "date_formats": {
            "short": "%Y/%m/%d",
            "medium": "%Y年%m月%d日",
            "long": "%Y年%m月%d日",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "今日",
            "yesterday": "昨日",
            "tomorrow": "明日",
            "days_ago": "{n}日前",
            "in_days": "{n}日後",
        },
    },
    "hi_IN": {
        "name": "हिन्दी (India)",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "currency_format": "{symbol}{amount}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d %B %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "आज",
            "yesterday": "कल",
            "tomorrow": "कल",
            "days_ago": "{n} दिन पहले",
            "in_days": "{n} दिन में",
        },
    },
    "zh_CN": {
        "name": "中文 (China)",
        "decimal_sep": ".",
        "thousands_sep": ",",
        "currency_format": "{symbol}{amount}",
        "date_formats": {
            "short": "%Y/%m/%d",
            "medium": "%Y年%m月%d日",
            "long": "%Y年%m月%d日",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "今天",
            "yesterday": "昨天",
            "tomorrow": "明天",
            "days_ago": "{n}天前",
            "in_days": "{n}天后",
        },
    },
    "es_ES": {
        "name": "Español (Spain)",
        "decimal_sep": ",",
        "thousands_sep": ".",
        "currency_format": "{amount} {symbol}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d de %B de %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Hoy",
            "yesterday": "Ayer",
            "tomorrow": "Mañana",
            "days_ago": "hace {n} días",
            "in_days": "en {n} días",
        },
    },
    "pt_BR": {
        "name": "Português (Brazil)",
        "decimal_sep": ",",
        "thousands_sep": ".",
        "currency_format": "{symbol} {amount}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d de %B de %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "Hoje",
            "yesterday": "Ontem",
            "tomorrow": "Amanhã",
            "days_ago": "há {n} dias",
            "in_days": "em {n} dias",
        },
    },
    "ar_SA": {
        "name": "العربية (Saudi Arabia)",
        "decimal_sep": "٫",
        "thousands_sep": "٬",
        "currency_format": "{amount} {symbol}",
        "date_formats": {
            "short": "%d/%m/%Y",
            "medium": "%d %b %Y",
            "long": "%d %B %Y",
            "iso": "%Y-%m-%d",
        },
        "relative_words": {
            "today": "اليوم",
            "yesterday": "أمس",
            "tomorrow": "غداً",
            "days_ago": "منذ {n} أيام",
            "in_days": "بعد {n} أيام",
        },
    },
}

# Currency symbol database
CURRENCY_SYMBOLS = {
    "USD": {"symbol": "$", "name": "US Dollar", "decimal_places": 2},
    "EUR": {"symbol": "€", "name": "Euro", "decimal_places": 2},
    "GBP": {"symbol": "£", "name": "British Pound", "decimal_places": 2},
    "INR": {"symbol": "₹", "name": "Indian Rupee", "decimal_places": 2},
    "JPY": {"symbol": "¥", "name": "Japanese Yen", "decimal_places": 0},
    "CNY": {"symbol": "¥", "name": "Chinese Yuan", "decimal_places": 2},
    "KRW": {"symbol": "₩", "name": "South Korean Won", "decimal_places": 0},
    "BRL": {"symbol": "R$", "name": "Brazilian Real", "decimal_places": 2},
    "CAD": {"symbol": "CA$", "name": "Canadian Dollar", "decimal_places": 2},
    "AUD": {"symbol": "A$", "name": "Australian Dollar", "decimal_places": 2},
    "CHF": {"symbol": "CHF", "name": "Swiss Franc", "decimal_places": 2},
    "MXN": {"symbol": "MX$", "name": "Mexican Peso", "decimal_places": 2},
    "SGD": {"symbol": "S$", "name": "Singapore Dollar", "decimal_places": 2},
    "HKD": {"symbol": "HK$", "name": "Hong Kong Dollar", "decimal_places": 2},
    "SEK": {"symbol": "kr", "name": "Swedish Krona", "decimal_places": 2},
    "NOK": {"symbol": "kr", "name": "Norwegian Krone", "decimal_places": 2},
    "DKK": {"symbol": "kr", "name": "Danish Krone", "decimal_places": 2},
    "PLN": {"symbol": "zł", "name": "Polish Zloty", "decimal_places": 2},
    "RUB": {"symbol": "₽", "name": "Russian Ruble", "decimal_places": 2},
    "TRY": {"symbol": "₺", "name": "Turkish Lira", "decimal_places": 2},
    "SAR": {"symbol": "﷼", "name": "Saudi Riyal", "decimal_places": 2},
    "AED": {"symbol": "د.إ", "name": "UAE Dirham", "decimal_places": 2},
    "THB": {"symbol": "฿", "name": "Thai Baht", "decimal_places": 2},
    "ZAR": {"symbol": "R", "name": "South African Rand", "decimal_places": 2},
    "NZD": {"symbol": "NZ$", "name": "New Zealand Dollar", "decimal_places": 2},
}

# Common timezones
COMMON_TIMEZONES = [
    "UTC",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Toronto",
    "America/Sao_Paulo",
    "America/Mexico_City",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "Europe/Moscow",
    "Asia/Tokyo",
    "Asia/Shanghai",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Dubai",
    "Asia/Seoul",
    "Australia/Sydney",
    "Pacific/Auckland",
    "Africa/Johannesburg",
    "Africa/Cairo",
]


def _get_locale_config(locale: str) -> dict:
    """Get locale configuration, falling back to en_US."""
    return LOCALE_CONFIG.get(locale, LOCALE_CONFIG["en_US"])


# ─── Number Formatting ──────────────────────────────────────────────


def format_number(
    value: float | Decimal | int,
    locale: str = "en_US",
    decimal_places: int = 2,
    use_grouping: bool = True,
) -> str:
    """Format a number according to locale conventions.

    Args:
        value: The number to format
        locale: Locale code (e.g., 'en_US', 'de_DE')
        decimal_places: Number of decimal places
        use_grouping: Whether to use thousands separators

    Returns:
        Formatted number string
    """
    config = _get_locale_config(locale)
    decimal_sep = config["decimal_sep"]
    thousands_sep = config["thousands_sep"]

    # Convert to Decimal for precision
    if isinstance(value, float):
        d = Decimal(str(value))
    elif isinstance(value, int):
        d = Decimal(value)
    else:
        d = value

    # Round to specified decimal places
    if decimal_places >= 0:
        quantize_str = "1." + "0" * decimal_places if decimal_places > 0 else "1"
        d = d.quantize(Decimal(quantize_str), rounding=ROUND_HALF_UP)

    # Split into integer and decimal parts
    str_val = str(abs(d))
    is_negative = d < 0

    if "." in str_val:
        int_part, dec_part = str_val.split(".")
    else:
        int_part = str_val
        dec_part = ""

    # Add grouping
    if use_grouping and len(int_part) > 3:
        groups = []
        for i in range(len(int_part), 0, -3):
            start = max(0, i - 3)
            groups.insert(0, int_part[start:i])
        int_part = thousands_sep.join(groups)

    # Assemble
    if decimal_places > 0 and dec_part:
        result = f"{int_part}{decimal_sep}{dec_part}"
    elif decimal_places > 0:
        result = f"{int_part}{decimal_sep}{'0' * decimal_places}"
    else:
        result = int_part

    if is_negative:
        result = f"-{result}"

    return result


def format_percentage(
    value: float | Decimal,
    locale: str = "en_US",
    decimal_places: int = 1,
) -> str:
    """Format a value as a percentage with locale-aware number formatting."""
    formatted = format_number(value, locale, decimal_places)
    return f"{formatted}%"


def format_compact_number(value: float | int, locale: str = "en_US") -> str:
    """Format large numbers in compact form (e.g., 1.2K, 3.4M)."""
    abs_val = abs(value)
    sign = "-" if value < 0 else ""

    if abs_val >= 1_000_000_000:
        return f"{sign}{format_number(abs_val / 1_000_000_000, locale, 1)}B"
    elif abs_val >= 1_000_000:
        return f"{sign}{format_number(abs_val / 1_000_000, locale, 1)}M"
    elif abs_val >= 1_000:
        return f"{sign}{format_number(abs_val / 1_000, locale, 1)}K"
    else:
        return f"{sign}{format_number(abs_val, locale, 0)}"


# ─── Currency Formatting ────────────────────────────────────────────


def format_currency(
    amount: float | Decimal,
    currency: str = "INR",
    locale: str = "en_US",
    display: str = "symbol",
    compact: bool = False,
) -> str:
    """Format a monetary amount with locale-aware formatting.

    Args:
        amount: The monetary value
        currency: ISO 4217 currency code
        locale: Locale code
        display: 'symbol', 'code', or 'name'
        compact: Use compact notation for large values

    Returns:
        Formatted currency string
    """
    config = _get_locale_config(locale)
    curr_info = CURRENCY_SYMBOLS.get(currency, {"symbol": currency, "name": currency, "decimal_places": 2})

    decimal_places = curr_info["decimal_places"]

    if compact:
        formatted_amount = format_compact_number(float(amount), locale)
    else:
        formatted_amount = format_number(amount, locale, decimal_places)

    # Determine symbol to use
    if display == "code":
        symbol = currency
    elif display == "name":
        symbol = curr_info["name"]
    else:
        symbol = curr_info["symbol"]

    # Apply locale-specific currency format
    template = config["currency_format"]
    return template.format(symbol=symbol, amount=formatted_amount)


# ─── Date Formatting ────────────────────────────────────────────────


def format_date(
    value: date | datetime | str,
    locale: str = "en_US",
    style: str = "medium",
    relative: bool = False,
) -> str:
    """Format a date with locale-aware formatting.

    Args:
        value: Date to format (date, datetime, or ISO string)
        locale: Locale code
        style: 'short', 'medium', 'long', or 'iso'
        relative: If True, use relative dates for recent dates

    Returns:
        Formatted date string
    """
    config = _get_locale_config(locale)

    # Parse string dates
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value).date()
        except (ValueError, TypeError):
            return value
    elif isinstance(value, datetime):
        value = value.date()

    # Relative formatting
    if relative:
        today = date.today()
        delta = (value - today).days
        words = config["relative_words"]

        if delta == 0:
            return words["today"]
        elif delta == -1:
            return words["yesterday"]
        elif delta == 1:
            return words["tomorrow"]
        elif -7 <= delta < 0:
            return words["days_ago"].format(n=abs(delta))
        elif 0 < delta <= 7:
            return words["in_days"].format(n=delta)

    # Standard formatting
    fmt = config["date_formats"].get(style, config["date_formats"]["medium"])
    return value.strftime(fmt)


def format_datetime(
    value: datetime | str,
    locale: str = "en_US",
    style: str = "medium",
    include_time: bool = True,
) -> str:
    """Format a datetime with locale-aware formatting."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except (ValueError, TypeError):
            return value

    date_str = format_date(value.date(), locale, style)

    if include_time:
        time_str = value.strftime("%H:%M")
        return f"{date_str} {time_str}"

    return date_str


# ─── User Preferences ───────────────────────────────────────────────


def get_user_locale_preferences(user_id: int) -> dict:
    """Get the locale preferences for a user."""
    user = db.session.get(User, user_id)
    if not user:
        return {
            "locale": "en_US",
            "timezone": "UTC",
            "date_format": "medium",
            "number_format": "standard",
            "currency": "INR",
            "currency_display": "symbol",
        }

    return {
        "locale": user.locale,
        "timezone": user.timezone,
        "date_format": user.date_format,
        "number_format": user.number_format,
        "currency": user.preferred_currency,
        "currency_display": user.currency_display,
    }


def update_user_locale_preferences(user_id: int, preferences: dict) -> dict:
    """Update locale preferences for a user.

    Args:
        user_id: The user ID
        preferences: Dict with keys: locale, timezone, date_format,
                     number_format, currency_display

    Returns:
        Updated preferences dict
    """
    user = db.session.get(User, user_id)
    if not user:
        return None

    valid_locales = set(LOCALE_CONFIG.keys())

    if "locale" in preferences:
        locale = preferences["locale"]
        if locale in valid_locales:
            user.locale = locale

    if "timezone" in preferences:
        tz = preferences["timezone"]
        if tz in COMMON_TIMEZONES or re.match(r"^[A-Za-z]+/[A-Za-z_]+$", tz):
            user.timezone = tz

    if "date_format" in preferences:
        if preferences["date_format"] in ("short", "medium", "long", "iso"):
            user.date_format = preferences["date_format"]

    if "number_format" in preferences:
        if preferences["number_format"] in ("standard", "compact"):
            user.number_format = preferences["number_format"]

    if "currency_display" in preferences:
        if preferences["currency_display"] in ("symbol", "code", "name"):
            user.currency_display = preferences["currency_display"]

    if "currency" in preferences:
        if preferences["currency"] in CURRENCY_SYMBOLS:
            user.preferred_currency = preferences["currency"]

    db.session.commit()
    return get_user_locale_preferences(user_id)


# ─── Bulk Formatting Helpers ────────────────────────────────────────


def format_expense_for_locale(expense_data: dict, locale: str = "en_US",
                               currency_display: str = "symbol",
                               date_style: str = "medium") -> dict:
    """Format an expense dict for a specific locale.

    Takes raw expense data and returns a copy with formatted fields.
    """
    formatted = dict(expense_data)

    if "amount" in formatted:
        currency = formatted.get("currency", "INR")
        formatted["amount_formatted"] = format_currency(
            formatted["amount"], currency, locale, currency_display
        )

    if "spent_at" in formatted:
        formatted["spent_at_formatted"] = format_date(
            formatted["spent_at"], locale, date_style
        )

    return formatted


def format_bill_for_locale(bill_data: dict, locale: str = "en_US",
                            currency_display: str = "symbol",
                            date_style: str = "medium") -> dict:
    """Format a bill dict for a specific locale."""
    formatted = dict(bill_data)

    if "amount" in formatted:
        currency = formatted.get("currency", "INR")
        formatted["amount_formatted"] = format_currency(
            formatted["amount"], currency, locale, currency_display
        )

    if "next_due_date" in formatted:
        formatted["next_due_date_formatted"] = format_date(
            formatted["next_due_date"], locale, date_style, relative=True
        )

    return formatted


def get_available_locales() -> list[dict]:
    """Return list of all supported locales with metadata."""
    result = []
    for code, config in LOCALE_CONFIG.items():
        result.append({
            "code": code,
            "name": config["name"],
            "decimal_separator": config["decimal_sep"],
            "thousands_separator": config["thousands_sep"],
            "sample_number": format_number(1234567.89, code),
            "sample_date": format_date(date.today(), code, "medium"),
        })
    return result


def get_supported_currencies() -> list[dict]:
    """Return list of all supported currencies."""
    result = []
    for code, info in CURRENCY_SYMBOLS.items():
        result.append({
            "code": code,
            "symbol": info["symbol"],
            "name": info["name"],
            "decimal_places": info["decimal_places"],
            "sample": format_currency(1234.56, code, "en_US"),
        })
    return result


def get_formatting_preview(locale: str, currency: str = "USD",
                            currency_display: str = "symbol") -> dict:
    """Get a preview of how data will look with given locale settings."""
    now = datetime.utcnow()
    sample_amount = Decimal("12345.67")

    return {
        "locale": locale,
        "currency": currency,
        "samples": {
            "number": format_number(12345.67, locale),
            "percentage": format_percentage(85.5, locale),
            "compact_number": format_compact_number(1500000, locale),
            "currency_small": format_currency(42.50, currency, locale, currency_display),
            "currency_large": format_currency(sample_amount, currency, locale, currency_display),
            "currency_compact": format_currency(1500000, currency, locale, currency_display, compact=True),
            "date_short": format_date(now, locale, "short"),
            "date_medium": format_date(now, locale, "medium"),
            "date_long": format_date(now, locale, "long"),
            "date_relative_today": format_date(date.today(), locale, "medium", relative=True),
        },
    }
