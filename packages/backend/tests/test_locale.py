"""
Tests for locale-aware formatting service.
"""

import pytest
from datetime import date
from app.services.locale import (
    format_currency,
    format_number,
    format_date,
    parse_locale_number,
    get_supported_locales,
    LOCALE_CONFIGS,
)


class TestCurrencyFormatting:
    def test_usd(self):
        result = format_currency(1234.56, "en-US")
        assert "$1,234.56" == result

    def test_eur_german(self):
        result = format_currency(1234.56, "de-DE")
        assert "1.234,56" in result
        assert "\u20ac" in result or "EUR" in result

    def test_jpy(self):
        result = format_currency(100000, "ja-JP")
        assert "100,000" in result

    def test_cny(self):
        result = format_currency(8888.88, "zh-CN")
        assert "8,888.88" in result

    def test_negative(self):
        result = format_currency(-100, "en-US")
        assert "-" in result
        assert "100" in result

    def test_zero(self):
        result = format_currency(0, "en-US")
        assert "$0.00" == result

    def test_default_locale(self):
        result = format_currency(100)
        assert "$" in result

    def test_unknown_locale_fallback(self):
        result = format_currency(100, "xx-XX")
        assert "$" in result  # Falls back to en-US


class TestNumberFormatting:
    def test_us(self):
        assert format_number(1234.56, "en-US") == "1,234.56"

    def test_german(self):
        assert format_number(1234.56, "de-DE") == "1.234,56"

    def test_decimals(self):
        result = format_number(100, "en-US", decimals=0)
        assert "100" == result

    def test_negative(self):
        result = format_number(-500, "en-US")
        assert result.startswith("-")


class TestDateFormatting:
    def test_us_medium(self):
        d = date(2024, 6, 15)
        result = format_date(d, "en-US", "medium")
        assert "06" in result or "6" in result
        assert "2024" in result

    def test_chinese(self):
        d = date(2024, 6, 15)
        result = format_date(d, "zh-CN")
        assert "2024" in result

    def test_short(self):
        d = date(2024, 6, 15)
        result = format_date(d, "en-US", "short")
        assert "24" in result


class TestParseLocaleNumber:
    def test_parse_us(self):
        assert parse_locale_number("1,234.56", "en-US") == 1234.56

    def test_parse_german(self):
        assert parse_locale_number("1.234,56", "de-DE") == 1234.56


class TestSupportedLocales:
    def test_list(self):
        locales = get_supported_locales()
        assert len(locales) >= 10
        locale_codes = [l["locale"] for l in locales]
        assert "en-US" in locale_codes
        assert "zh-CN" in locale_codes
        assert "ja-JP" in locale_codes
