"""
Tests for locale-aware date, currency & number formatting (Issue #131).

Covers:
- format_currency: symbol position, decimal/thousands separators per locale
- format_number: thousands separators per locale
- format_date: date pattern per locale + style variants
- format_datetime: combined date + time
- GET /locale/supported returns all locales
- GET /locale/info returns metadata
- POST /locale/format formats values with given locale
- GET /locale/preview returns user's locale examples
- PATCH /auth/me sets preferred_locale
- GET /auth/me returns preferred_locale
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.services.locale_fmt import (
    SUPPORTED_LOCALES,
    format_currency,
    format_date,
    format_datetime,
    format_number,
    get_locale_info,
)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — formatting service
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatCurrency:
    def test_usd_en_us(self):
        result = format_currency(1234.56, "USD", "en_US")
        assert result == "$1,234.56"

    def test_eur_de_de_suffix(self):
        result = format_currency(1234.56, "EUR", "de_DE")
        assert "1.234,56" in result
        assert "€" in result

    def test_inr_en_in(self):
        result = format_currency(1234.56, "INR", "en_IN")
        assert "₹" in result
        assert "1,234.56" in result

    def test_gbp_en_gb(self):
        result = format_currency(1000, "GBP", "en_GB")
        assert "£" in result

    def test_zero_amount(self):
        result = format_currency(0, "USD", "en_US")
        assert "$0.00" == result

    def test_large_amount(self):
        result = format_currency(1000000, "USD", "en_US")
        assert "$1,000,000.00" == result

    def test_unknown_currency_uses_code(self):
        result = format_currency(100, "XYZ", "en_US")
        assert "XYZ" in result


class TestFormatNumber:
    def test_en_us_comma_thousands(self):
        assert format_number(1234567, "en_US") == "1,234,567"

    def test_de_de_dot_thousands(self):
        assert format_number(1234567, "de_DE") == "1.234.567"

    def test_with_decimals(self):
        result = format_number(1234.5, "en_US", decimals=2)
        assert result == "1,234.50"

    def test_zero(self):
        assert format_number(0, "en_US") == "0"


class TestFormatDate:
    _date = date(2026, 3, 14)

    def test_en_us_short(self):
        result = format_date(self._date, "en_US", "short")
        assert result == "03/14/2026"

    def test_de_de_short(self):
        result = format_date(self._date, "de_DE", "short")
        assert result == "14.03.2026"

    def test_medium_style(self):
        result = format_date(self._date, "en_US", "medium")
        assert "Mar" in result and "2026" in result

    def test_iso_style(self):
        assert format_date(self._date, "en_US", "iso") == "2026-03-14"

    def test_long_style(self):
        result = format_date(self._date, "en_US", "long")
        assert "March" in result and "2026" in result

    def test_string_input(self):
        result = format_date("2026-03-14", "en_US", "iso")
        assert result == "2026-03-14"


class TestFormatDatetime:
    def test_includes_time(self):
        dt = datetime(2026, 3, 14, 10, 30)
        result = format_datetime(dt, "en_US")
        assert "10:30" in result or "AM" in result or "PM" in result


class TestGetLocaleInfo:
    def test_en_us(self):
        info = get_locale_info("en_US")
        assert info["decimal_separator"] == "."
        assert info["thousands_separator"] == ","
        assert info["currency_symbol_position"] == "prefix"
        assert info["supported"] is True

    def test_de_de(self):
        info = get_locale_info("de_DE")
        assert info["decimal_separator"] == ","
        assert info["thousands_separator"] == "."
        assert info["currency_symbol_position"] == "suffix"

    def test_unknown_falls_back(self):
        info = get_locale_info("xx_XX")
        assert info["supported"] is False


class TestSupportedLocales:
    def test_common_locales_present(self):
        assert "en_US" in SUPPORTED_LOCALES
        assert "de_DE" in SUPPORTED_LOCALES
        assert "en_IN" in SUPPORTED_LOCALES
        assert "ja_JP" in SUPPORTED_LOCALES


# ─────────────────────────────────────────────────────────────────────────────
# Integration tests — HTTP endpoints
# ─────────────────────────────────────────────────────────────────────────────

def _auth(client, email="loc@test.com"):
    client.post("/auth/register", json={"email": email, "password": "pass1234"})
    r = client.post("/auth/login", json={"email": email, "password": "pass1234"})
    return {"Authorization": f"Bearer {r.get_json()['access_token']}"}


class TestLocaleEndpoints:
    def test_supported_locales(self, client, app_fixture):
        r = client.get("/locale/supported")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 5
        assert any(d["locale"] == "en_US" for d in data)

    def test_locale_info(self, client, app_fixture):
        r = client.get("/locale/info?locale=de_DE")
        assert r.status_code == 200
        d = r.get_json()
        assert d["decimal_separator"] == ","
        assert d["locale"] == "de_DE"

    def test_format_amounts(self, client, app_fixture):
        h = _auth(client, "fmt1@test.com")
        r = client.post("/locale/format", json={
            "locale": "en_US",
            "currency": "USD",
            "amounts": [1234.56, 999.99],
        }, headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert d["formatted_amounts"][0] == "$1,234.56"
        assert d["formatted_amounts"][1] == "$999.99"

    def test_format_numbers(self, client, app_fixture):
        h = _auth(client, "fmt2@test.com")
        r = client.post("/locale/format", json={
            "locale": "de_DE",
            "numbers": [1234567],
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["formatted_numbers"][0] == "1.234.567"

    def test_format_dates(self, client, app_fixture):
        h = _auth(client, "fmt3@test.com")
        r = client.post("/locale/format", json={
            "locale": "en_US",
            "dates": ["2026-03-14"],
            "date_style": "iso",
        }, headers=h)
        assert r.status_code == 200
        assert r.get_json()["formatted_dates"][0] == "2026-03-14"

    def test_format_requires_auth(self, client, app_fixture):
        r = client.post("/locale/format", json={"amounts": [100]})
        assert r.status_code == 401

    def test_preview(self, client, app_fixture):
        h = _auth(client, "prev@test.com")
        r = client.get("/locale/preview", headers=h)
        assert r.status_code == 200
        d = r.get_json()
        assert "examples" in d
        assert "currency" in d["examples"]
        assert "date_medium" in d["examples"]

    def test_set_preferred_locale(self, client, app_fixture):
        h = _auth(client, "setloc@test.com")
        r = client.patch("/auth/me", json={"preferred_locale": "de_DE"}, headers=h)
        assert r.status_code == 200
        assert r.get_json()["preferred_locale"] == "de_DE"

    def test_get_me_includes_locale(self, client, app_fixture):
        h = _auth(client, "getloc@test.com")
        r = client.get("/auth/me", headers=h)
        assert r.status_code == 200
        assert "preferred_locale" in r.get_json()

    def test_invalid_locale_rejected(self, client, app_fixture):
        h = _auth(client, "badloc@test.com")
        r = client.patch("/auth/me", json={"preferred_locale": "xx_ZZ"}, headers=h)
        assert r.status_code == 400
