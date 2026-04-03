"""
Tests for locale-aware formatting service.
Issue #131: Verify all locale formatting functions.
"""

import pytest
from datetime import date
from packages.backend.app.services.locale_format import (
    format_currency,
    format_date,
    format_number,
    get_supported_locales,
    get_supported_currencies,
)


class TestFormatNumber:
    def test_us_format(self):
        assert format_number(1234567.89, locale="en-US", decimals=2) == "1,234,567.89"

    def test_de_format(self):
        assert format_number(1234567.89, locale="de-DE", decimals=2) == "1.234.567,89"

    def test_fr_format_non_breaking_space(self):
        result = format_number(1234567.89, locale="fr-FR", decimals=2)
        assert "1" in result and "234" in result and ",89" in result

    def test_zero_decimals(self):
        assert format_number(1234, locale="en-US", decimals=0) == "1,234"

    def test_negative_value(self):
        result = format_number(-100.5, locale="en-US", decimals=2)
        assert result.startswith("-")

    def test_small_number_no_separator(self):
        assert format_number(123, locale="en-US", decimals=2) == "123.00"

    def test_indian_format(self):
        result = format_number(1234567.89, locale="en-IN", decimals=2)
        assert "," in result


class TestFormatCurrency:
    def test_usd_en_us(self):
        assert format_currency(1234.56, "USD", locale="en-US") == "$1,234.56"

    def test_eur_de_de_symbol_after(self):
        result = format_currency(1234.56, "EUR", locale="de-DE")
        assert result.endswith("€") or " €" in result

    def test_inr_en_in(self):
        result = format_currency(1234.56, "INR", locale="en-IN")
        assert "₹" in result

    def test_jpy_no_decimals(self):
        result = format_currency(1234, "JPY", locale="ja-JP")
        assert "¥" in result
        assert "." not in result

    def test_gbp_symbol_before(self):
        result = format_currency(100.00, "GBP", locale="en-GB")
        assert result.startswith("£")

    def test_show_code(self):
        result = format_currency(100.00, "USD", locale="en-US", show_code=True)
        assert "USD" in result

    def test_unknown_currency_code(self):
        result = format_currency(100.00, "XYZ", locale="en-US")
        assert "XYZ" in result

    def test_zero_amount(self):
        result = format_currency(0, "USD", locale="en-US")
        assert "$" in result and "0" in result


class TestFormatDate:
    def test_us_medium(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="en-US", style="medium")
        assert "Apr" in result or "April" in result
        assert "3" in result

    def test_de_short(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="de-DE", style="short")
        assert result == "03.04.2026"

    def test_gb_short(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="en-GB", style="short")
        assert result == "03/04/2026"

    def test_us_short(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="en-US", style="short")
        assert result == "04/03/2026"

    def test_iso_style(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="en-US", style="iso")
        assert result == "2026-04-03"

    def test_none_returns_empty(self):
        assert format_date(None, locale="en-US") == ""

    def test_jp_format(self):
        d = date(2026, 4, 3)
        result = format_date(d, locale="ja-JP", style="medium")
        assert "年" in result or "2026" in result


class TestSupportedHelpers:
    def test_get_supported_locales_returns_list(self):
        locales = get_supported_locales()
        assert isinstance(locales, list)
        assert len(locales) > 10
        assert "en-US" in locales
        assert "de-DE" in locales

    def test_get_supported_currencies_returns_list(self):
        currencies = get_supported_currencies()
        assert isinstance(currencies, list)
        assert "USD" in currencies
        assert "EUR" in currencies
        assert "INR" in currencies
        assert len(currencies) > 30


class TestLocaleAPI:
    def test_format_currency_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/locale/format",
            json={"type": "currency", "value": 1234.56, "currency": "USD", "locale": "en-US"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["formatted"] == "$1,234.56"

    def test_format_number_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/locale/format",
            json={"type": "number", "value": 9876543.21, "locale": "de-DE", "decimals": 2},
            headers=auth_headers,
        )
        assert response.status_code == 200

    def test_format_date_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/locale/format",
            json={"type": "date", "value": "2026-04-03", "locale": "en-US", "style": "medium"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert "Apr" in data["formatted"] or "April" in data["formatted"]

    def test_supported_endpoint(self, client):
        response = client.get("/api/locale/supported")
        assert response.status_code == 200
        data = response.get_json()
        assert "locales" in data
        assert "currencies" in data

    def test_batch_format_endpoint(self, client, auth_headers):
        response = client.post(
            "/api/locale/format-batch",
            json={
                "locale": "en-US",
                "items": [
                    {"type": "currency", "value": 100.00, "currency": "USD"},
                    {"type": "number", "value": 1000},
                    {"type": "date", "value": "2026-04-03"},
                ]
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.get_json()
        assert len(data["results"]) == 3

    def test_requires_auth(self, client):
        response = client.post(
            "/api/locale/format",
            json={"type": "currency", "value": 100, "currency": "USD"},
        )
        assert response.status_code == 401

    def test_invalid_type_returns_400(self, client, auth_headers):
        response = client.post(
            "/api/locale/format",
            json={"type": "invalid", "value": 100},
            headers=auth_headers,
        )
        assert response.status_code == 400