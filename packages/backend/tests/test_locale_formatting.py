"""Tests for locale-aware formatting service."""
import pytest
from unittest.mock import patch
from datetime import date

from app.services.locale_formatting import (
    format_for_locale,
    list_supported_locales,
    _format_number,
    LOCALE_CONFIG,
)


# ──────────────────────────────────────────────
# Number formatting helpers
# ──────────────────────────────────────────────

def test_format_number_en_us():
    result = _format_number(1234567.89, ",", ".", 2)
    assert result == "1,234,567.89"


def test_format_number_de_de():
    # German uses . for thousands, , for decimal
    result = _format_number(1234567.89, ".", ",", 2)
    assert result == "1.234.567,89"


def test_format_number_fr_fr():
    # French uses space for thousands, , for decimal
    result = _format_number(1234567.89, " ", ",", 2)
    assert result == "1 234 567,89"


def test_format_number_negative():
    result = _format_number(-1234.56, ",", ".", 2)
    assert result == "-1,234.56"


def test_format_number_zero_decimals():
    result = _format_number(1234567.0, ",", ".", 0)
    assert result == "1,234,567"


# ──────────────────────────────────────────────
# format_for_locale — currency formatting
# ──────────────────────────────────────────────

def test_en_us_currency_before():
    r = format_for_locale("en-US", 1234.56, 100.0, "2026-01-15")
    assert r.formatted_currency.startswith("$")
    assert "1,234.56" in r.formatted_currency


def test_de_de_currency_after():
    r = format_for_locale("de-DE", 1234.56, 100.0, "2026-01-15")
    assert r.formatted_currency.endswith("€")
    assert "1.234,56" in r.formatted_currency


def test_fr_fr_currency_after():
    r = format_for_locale("fr-FR", 1234.56, 100.0, "2026-01-15")
    assert r.formatted_currency.endswith("€")


def test_ja_jp_no_decimals():
    r = format_for_locale("ja-JP", 1234.0, 100.0, "2026-01-15")
    # JPY has no decimals
    assert "." not in r.formatted_currency
    assert r.currency_code == "JPY"


def test_pt_br_currency_before():
    r = format_for_locale("pt-BR", 1234.56, 100.0, "2026-01-15")
    assert r.formatted_currency.startswith("R$")


# ──────────────────────────────────────────────
# format_for_locale — date formatting
# ──────────────────────────────────────────────

def test_en_us_date_long():
    r = format_for_locale("en-US", 100.0, 100.0, "2026-03-15")
    assert "March" in r.formatted_date
    assert "15" in r.formatted_date
    assert "2026" in r.formatted_date


def test_en_us_date_short():
    r = format_for_locale("en-US", 100.0, 100.0, "2026-03-15")
    assert r.formatted_date_short == "03/15/2026"


def test_de_de_date_short():
    r = format_for_locale("de-DE", 100.0, 100.0, "2026-03-15")
    assert r.formatted_date_short == "15.03.2026"


def test_ja_jp_date():
    r = format_for_locale("ja-JP", 100.0, 100.0, "2026-03-15")
    assert "2026年" in r.formatted_date
    assert "03月" in r.formatted_date


def test_date_defaults_to_today():
    today = date.today().isoformat()
    r = format_for_locale("en-US", 100.0, 100.0)
    assert r.input_date == today


def test_invalid_date_falls_back_to_today():
    today = date.today().isoformat()
    r = format_for_locale("en-US", 100.0, 100.0, "not-a-date")
    assert r.input_date == today


# ──────────────────────────────────────────────
# format_for_locale — locale fallback
# ──────────────────────────────────────────────

def test_unknown_locale_falls_back_to_en_us():
    r = format_for_locale("xx-XX", 1234.56, 100.0, "2026-01-15")
    # Falls back to en-US
    assert r.formatted_currency.startswith("$")


# ──────────────────────────────────────────────
# list_supported_locales
# ──────────────────────────────────────────────

def test_list_supported_locales_count():
    locales = list_supported_locales()
    assert len(locales) == len(LOCALE_CONFIG)


def test_list_supported_locales_fields():
    locales = list_supported_locales()
    for loc in locales:
        assert "locale" in loc
        assert "name" in loc
        assert "currency_code" in loc
        assert "currency_symbol" in loc