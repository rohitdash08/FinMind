"""Locale-aware date, currency & number formatting.

Per-user locale preferences with formatting utilities for
dates, currencies, and numbers.
"""

import locale as _locale
from datetime import datetime, date
from ..extensions import db


class UserLocale(db.Model):
    __tablename__ = "user_locales"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    language = db.Column(db.String(10), default="en")
    country = db.Column(db.String(10), default="US")
    currency = db.Column(db.String(3), default="USD")
    date_format = db.Column(db.String(20), default="YYYY-MM-DD")
    number_format = db.Column(db.String(20), default="1,234.56")  # grouping style
    timezone = db.Column(db.String(50), default="UTC")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


SUPPORTED_CURRENCIES = [
    {"code": "USD", "symbol": "$", "name": "US Dollar"},
    {"code": "EUR", "symbol": "€", "name": "Euro"},
    {"code": "GBP", "symbol": "£", "name": "British Pound"},
    {"code": "JPY", "symbol": "¥", "name": "Japanese Yen"},
    {"code": "CNY", "symbol": "¥", "name": "Chinese Yuan"},
    {"code": "KRW", "symbol": "₩", "name": "Korean Won"},
    {"code": "INR", "symbol": "₹", "name": "Indian Rupee"},
    {"code": "BRL", "symbol": "R$", "name": "Brazilian Real"},
    {"code": "CAD", "symbol": "CA$", "name": "Canadian Dollar"},
    {"code": "AUD", "symbol": "A$", "name": "Australian Dollar"},
]

DATE_FORMATS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "DD.MM.YYYY": "%d.%m.%Y",
    "YYYY年MM月DD日": "%Y年%m月%d日",
}

NUMBER_STYLES = {
    "1,234.56": {"group": ",", "decimal": "."},
    "1.234,56": {"group": ".", "decimal": ","},
    "1 234,56": {"group": " ", "decimal": ","},
    "1'234.56": {"group": "'", "decimal": "."},
}


def get_locale(user_id: int) -> dict:
    loc = UserLocale.query.filter_by(user_id=user_id).first()
    if not loc:
        loc = UserLocale(user_id=user_id)
        db.session.add(loc)
        db.session.commit()
    return _serialize(loc)


def update_locale(user_id: int, **kwargs) -> dict:
    loc = UserLocale.query.filter_by(user_id=user_id).first()
    if not loc:
        loc = UserLocale(user_id=user_id)
        db.session.add(loc)

    for key in ("language", "country", "currency", "date_format", "number_format", "timezone"):
        if key in kwargs and kwargs[key] is not None:
            if key == "currency" and kwargs[key] not in [c["code"] for c in SUPPORTED_CURRENCIES]:
                raise ValueError(f"Unsupported currency: {kwargs[key]}")
            if key == "date_format" and kwargs[key] not in DATE_FORMATS:
                raise ValueError(f"Unsupported date format: {kwargs[key]}")
            if key == "number_format" and kwargs[key] not in NUMBER_STYLES:
                raise ValueError(f"Unsupported number format: {kwargs[key]}")
            setattr(loc, key, kwargs[key])

    db.session.commit()
    return _serialize(loc)


def format_currency(user_id: int, amount: float) -> str:
    loc = UserLocale.query.filter_by(user_id=user_id).first()
    currency = loc.currency if loc else "USD"
    number_fmt = loc.number_format if loc else "1,234.56"

    symbol = next((c["symbol"] for c in SUPPORTED_CURRENCIES if c["code"] == currency), "$")
    formatted = _format_number(amount, number_fmt, decimals=2)
    return f"{symbol}{formatted}"


def format_date(user_id: int, d: date) -> str:
    loc = UserLocale.query.filter_by(user_id=user_id).first()
    fmt = loc.date_format if loc else "YYYY-MM-DD"
    py_fmt = DATE_FORMATS.get(fmt, "%Y-%m-%d")
    return d.strftime(py_fmt)


def format_number(user_id: int, value: float, decimals: int = 2) -> str:
    loc = UserLocale.query.filter_by(user_id=user_id).first()
    number_fmt = loc.number_format if loc else "1,234.56"
    return _format_number(value, number_fmt, decimals)


def get_supported_currencies() -> list[dict]:
    return SUPPORTED_CURRENCIES


def get_date_formats() -> list[str]:
    return list(DATE_FORMATS.keys())


def get_number_formats() -> list[str]:
    return list(NUMBER_STYLES.keys())


def _format_number(value: float, style: str, decimals: int = 2) -> str:
    fmt = NUMBER_STYLES.get(style, NUMBER_STYLES["1,234.56"])
    negative = value < 0
    value = abs(value)

    int_part = int(value)
    dec_part = round(value - int_part, decimals)
    dec_str = f"{dec_part:.{decimals}f}"[2:]  # strip "0."

    # Group digits
    int_str = str(int_part)
    groups = []
    while int_str:
        groups.append(int_str[-3:])
        int_str = int_str[:-3]
    grouped = fmt["group"].join(reversed(groups))

    result = f"{grouped}{fmt['decimal']}{dec_str}" if decimals > 0 else grouped
    return f"-{result}" if negative else result


def _serialize(loc: UserLocale) -> dict:
    return {
        "language": loc.language, "country": loc.country,
        "currency": loc.currency, "date_format": loc.date_format,
        "number_format": loc.number_format, "timezone": loc.timezone,
    }
