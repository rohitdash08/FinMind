import logging
from datetime import date, datetime
from typing import Any

logger = logging.getLogger("finmind.i18n")

LOCALE_MAP: dict[str, dict[str, Any]] = {
    "en-US": {
        "currency": {"symbol": "$", "code": "USD", "decimal": ".", "group": ","},
        "date": {"short": "%m/%d/%Y", "long": "%B %d, %Y"},
        "number": {"decimal": ".", "group": ","},
    },
    "en-IN": {
        "currency": {"symbol": "\u20b9", "code": "INR", "decimal": ".", "group": ","},
        "date": {"short": "%d/%m/%Y", "long": "%d %B %Y"},
        "number": {"decimal": ".", "group": ","},
    },
    "en-GB": {
        "currency": {"symbol": "\u00a3", "code": "GBP", "decimal": ".", "group": ","},
        "date": {"short": "%d/%m/%Y", "long": "%d %B %Y"},
        "number": {"decimal": ".", "group": ","},
    },
    "de-DE": {
        "currency": {"symbol": "\u20ac", "code": "EUR", "decimal": ",", "group": "."},
        "date": {"short": "%d.%m.%Y", "long": "%d. %B %Y"},
        "number": {"decimal": ",", "group": "."},
    },
    "fr-FR": {
        "currency": {"symbol": "\u20ac", "code": "EUR", "decimal": ",", "group": " "},
        "date": {"short": "%d/%m/%Y", "long": "%d %B %Y"},
        "number": {"decimal": ",", "group": " "},
    },
    "ja-JP": {
        "currency": {"symbol": "\u00a5", "code": "JPY", "decimal": ".", "group": ","},
        "date": {"short": "%Y/%m/%d", "long": "%Y\u5e74%m\u6708%d\u65e5"},
        "number": {"decimal": ".", "group": ","},
    },
    "en-SG": {
        "currency": {"symbol": "S$", "code": "SGD", "decimal": ".", "group": ","},
        "date": {"short": "%d/%m/%Y", "long": "%d %B %Y"},
        "number": {"decimal": ".", "group": ","},
    },
    "en-AE": {
        "currency": {"symbol": "\u062f.\u0625", "code": "AED", "decimal": ".", "group": ","},
        "date": {"short": "%d/%m/%Y", "long": "%d %B %Y"},
        "number": {"decimal": ".", "group": ","},
    },
}


def get_locale(locale_str: str = "en-US") -> dict[str, Any]:
    return LOCALE_MAP.get(locale_str, LOCALE_MAP["en-US"])


def list_locales() -> list[str]:
    return list(LOCALE_MAP.keys())


def format_currency(amount: float, locale_str: str = "en-US", currency_code: str | None = None) -> str:
    locale_cfg = get_locale(locale_str)
    curr = locale_cfg["currency"]
    dec = curr["decimal"]
    grp = curr["group"]
    symbol = curr["symbol"]
    code = currency_code or curr["code"]
    integer_part, fractional_part = f"{amount:.2f}".split(".")
    integer_part = _add_group_separator(integer_part, grp)
    formatted = f"{symbol}{integer_part}{dec}{fractional_part}"
    return formatted


def format_date(date_val: str | date, locale_str: str = "en-US", style: str = "short") -> str:
    locale_cfg = get_locale(locale_str)
    fmt = locale_cfg["date"].get(style, locale_cfg["date"]["short"])
    if isinstance(date_val, str):
        try:
            d = date.fromisoformat(date_val)
        except ValueError:
            return date_val
    else:
        d = date_val
    return d.strftime(fmt)


def format_number(value: float, locale_str: str = "en-US", decimals: int = 2) -> str:
    locale_cfg = get_locale(locale_str)
    num = locale_cfg["number"]
    dec = num["decimal"]
    grp = num["group"]
    formatted = f"{value:.{decimals}f}"
    integer_part, fractional_part = formatted.split(".")
    integer_part = _add_group_separator(integer_part, grp)
    return f"{integer_part}{dec}{fractional_part}"


def detect_locale_from_headers(accept_language: str | None = None) -> str:
    if not accept_language:
        return "en-US"
    locales = accept_language.split(",")
    for entry in locales:
        tag = entry.split(";")[0].strip().replace("-", "_")
        lang_variants = [tag, tag.replace("_", "-")]
        for variant in lang_variants:
            if variant in LOCALE_MAP:
                return variant
        lang = tag.split("_")[0]
        for key in LOCALE_MAP:
            if key.startswith(lang):
                return key
    return "en-US"


def _add_group_separator(integer_part: str, group_sep: str) -> str:
    result = ""
    for i, ch in enumerate(reversed(integer_part)):
        if i > 0 and i % 3 == 0:
            result = group_sep + result
        result = ch + result
    return result
