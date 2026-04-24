from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import Request


DEFAULT_LOCALE = "en-IN"
SUPPORTED_LOCALES = {
    "en-US": {
        "currency_position": "prefix",
        "decimal": ".",
        "thousands": ",",
        "date_order": "mdy",
    },
    "en-IN": {
        "currency_position": "prefix",
        "decimal": ".",
        "thousands": ",",
        "date_order": "dmy",
        "indian_grouping": True,
    },
    "en-GB": {
        "currency_position": "prefix",
        "decimal": ".",
        "thousands": ",",
        "date_order": "dmy",
    },
    "de-DE": {
        "currency_position": "suffix",
        "decimal": ",",
        "thousands": ".",
        "date_order": "dmy_dot",
    },
    "fr-FR": {
        "currency_position": "suffix",
        "decimal": ",",
        "thousands": " ",
        "date_order": "dmy_slash",
    },
    "ja-JP": {
        "currency_position": "prefix",
        "decimal": ".",
        "thousands": ",",
        "date_order": "ymd",
    },
}

CURRENCY_SYMBOLS = {
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


def resolve_locale(req: Request | None) -> str:
    """Resolve a safe, deterministic locale from query string or Accept-Language."""
    candidates: list[str] = []
    if req is not None:
        explicit = (req.args.get("locale") or "").strip()
        if explicit:
            candidates.append(explicit)
        header = req.headers.get("Accept-Language", "")
        candidates.extend(part.split(";", 1)[0].strip() for part in header.split(","))

    for candidate in candidates:
        normalized = _normalize_locale(candidate)
        if normalized in SUPPORTED_LOCALES:
            return normalized
        language = normalized.split("-", 1)[0]
        for supported in SUPPORTED_LOCALES:
            if supported.startswith(language + "-"):
                return supported
    return DEFAULT_LOCALE


def format_money(amount, currency: str | None = None, locale: str | None = None) -> str:
    code = (currency or "INR").upper()
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    spec = SUPPORTED_LOCALES[loc]
    decimals = 0 if code == "JPY" else 2
    number = format_number(amount, locale=loc, decimals=decimals)
    symbol = CURRENCY_SYMBOLS.get(code, code)
    if spec["currency_position"] == "suffix":
        return f"{number} {symbol}"
    return f"{symbol}{number}"


def format_number(value, locale: str | None = None, decimals: int = 2) -> str:
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    spec = SUPPORTED_LOCALES[loc]
    try:
        quant = Decimal("1") if decimals == 0 else Decimal("1").scaleb(-decimals)
        amount = Decimal(str(value)).quantize(quant)
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0").quantize(Decimal("1").scaleb(-decimals))

    sign = "-" if amount < 0 else ""
    raw = f"{abs(amount):.{decimals}f}"
    whole, _, fraction = raw.partition(".")
    grouped = (
        _group_indian(whole, spec["thousands"])
        if spec.get("indian_grouping")
        else _group_standard(whole, spec["thousands"])
    )
    if decimals == 0:
        return sign + grouped
    return sign + grouped + spec["decimal"] + fraction


def format_date(
    value: date | datetime | str | None, locale: str | None = None
) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        parsed = date.fromisoformat(value[:10])
    elif isinstance(value, datetime):
        parsed = value.date()
    else:
        parsed = value
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    order = SUPPORTED_LOCALES[loc]["date_order"]
    if order == "mdy":
        return parsed.strftime("%m/%d/%Y")
    if order == "ymd":
        return parsed.strftime("%Y/%m/%d")
    if order == "dmy_dot":
        return parsed.strftime("%d.%m.%Y")
    return parsed.strftime("%d/%m/%Y")


def money_payload(
    amount, currency: str | None = None, locale: str | None = None
) -> dict:
    loc = locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE
    return {
        "locale": loc,
        "currency": (currency or "INR").upper(),
        "amount": float(amount or 0),
        "amount_formatted": format_money(amount, currency, loc),
    }


def _normalize_locale(raw: str) -> str:
    cleaned = raw.replace("_", "-").strip()
    if not cleaned:
        return ""
    parts = cleaned.split("-")
    if len(parts) == 1:
        return parts[0].lower()
    return f"{parts[0].lower()}-{parts[1].upper()}"


def _group_standard(whole: str, sep: str) -> str:
    groups = []
    while whole:
        groups.append(whole[-3:])
        whole = whole[:-3]
    return sep.join(reversed(groups)) if groups else "0"


def _group_indian(whole: str, sep: str) -> str:
    if len(whole) <= 3:
        return whole
    last = whole[-3:]
    rest = whole[:-3]
    groups = []
    while rest:
        groups.append(rest[-2:])
        rest = rest[:-2]
    return sep.join(reversed(groups)) + sep + last
