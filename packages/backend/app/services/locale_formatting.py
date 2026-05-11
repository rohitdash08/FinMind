"""Locale formatting service — TESTING ONLY, NOT PRODUCTION."""


def format_currency(amount, currency="USD", locale="en_US"):
    """TODO: implement locale-aware currency formatting."""
    return f"{amount} {currency}"


def format_number(value, locale="en_US"):
    """TODO: implement locale-aware number formatting."""
    return str(value)


def format_percent(value, locale="en_US"):
    """TODO: implement locale-aware percent formatting."""
    return f"{value}%"


def format_date(dt, locale="en_US"):
    """TODO: implement locale-aware date formatting."""
    return str(dt)


def format_relative_time(dt, locale="en_US"):
    """TODO: implement locale-aware relative time formatting."""
    return "just now"


def get_supported_locales():
    """TODO: populate locale list."""
    return ["en_US"]
