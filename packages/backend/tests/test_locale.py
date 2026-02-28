"""Tests for locale-aware formatting service and API."""

import pytest
from datetime import datetime, date
from app.services.locale_formatting import (
    format_currency,
    format_number,
    format_percent,
    format_date,
    format_datetime,
    format_relative_time,
    get_supported_locales,
    get_currency_for_locale,
)


class TestFormatCurrency:
    def test_usd_default(self):
        result = format_currency(1234.56)
        assert "$" in result
        assert "1,234.56" in result

    def test_eur_german(self):
        result = format_currency(1234.56, locale_str="de_DE")
        assert "€" in result

    def test_jpy(self):
        result = format_currency(1234, currency="JPY", locale_str="ja_JP")
        assert "￥" in result or "¥" in result

    def test_cny(self):
        result = format_currency(9999.99, locale_str="zh_CN")
        assert "¥" in result or "CN" in result

    def test_explicit_currency_override(self):
        result = format_currency(100, currency="GBP", locale_str="en_US")
        assert "£" in result


class TestFormatNumber:
    def test_default(self):
        result = format_number(1234567.89)
        assert "1,234,567" in result

    def test_fixed_decimals(self):
        result = format_number(1234.5, decimal_places=2)
        assert "1,234.50" in result

    def test_german_separators(self):
        result = format_number(1234567.89, locale_str="de_DE")
        assert "1.234.567" in result


class TestFormatPercent:
    def test_default(self):
        result = format_percent(0.156)
        assert "15.6%" in result

    def test_zero_decimals(self):
        result = format_percent(0.5, decimal_places=0)
        assert "50%" in result


class TestFormatDate:
    def test_medium(self):
        dt = date(2026, 2, 28)
        result = format_date(dt, format="medium")
        assert "2026" in result

    def test_chinese_locale(self):
        dt = date(2026, 2, 28)
        result = format_date(dt, format="long", locale_str="zh_CN")
        assert "2026" in result

    def test_short(self):
        dt = date(2026, 12, 25)
        result = format_date(dt, format="short")
        assert len(result) > 0


class TestFormatDatetime:
    def test_medium(self):
        dt = datetime(2026, 2, 28, 14, 30, 0)
        result = format_datetime(dt, format="medium")
        assert "2026" in result


class TestRelativeTime:
    def test_past(self):
        now = datetime(2026, 2, 28, 12, 0, 0)
        dt = datetime(2026, 2, 25, 12, 0, 0)
        result = format_relative_time(dt, now=now)
        assert "3" in result and "day" in result

    def test_chinese(self):
        now = datetime(2026, 2, 28, 12, 0, 0)
        dt = datetime(2026, 2, 27, 12, 0, 0)
        result = format_relative_time(dt, now=now, locale_str="zh_CN")
        assert len(result) > 0


class TestHelpers:
    def test_supported_locales(self):
        locales = get_supported_locales()
        assert "en_US" in locales
        assert "zh_CN" in locales
        assert len(locales) >= 10

    def test_currency_for_locale(self):
        assert get_currency_for_locale("en_US") == "USD"
        assert get_currency_for_locale("ja_JP") == "JPY"
        assert get_currency_for_locale("unknown") == "USD"


class TestLocaleAPI:
    def test_list_locales(self, client):
        resp = client.get("/locale/locales")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data) >= 10
        assert any(loc["locale"] == "en_US" for loc in data)

    def test_format_currency_api(self, client):
        resp = client.post("/locale/format/currency", json={"amount": 1234.56})
        assert resp.status_code == 200
        data = resp.get_json()
        assert "$" in data["formatted"]

    def test_format_currency_with_locale(self, client):
        resp = client.post(
            "/locale/format/currency",
            json={"amount": 1234.56, "locale": "de_DE"},
        )
        assert resp.status_code == 200
        assert "€" in resp.get_json()["formatted"]

    def test_format_currency_missing_amount(self, client):
        resp = client.post("/locale/format/currency", json={})
        assert resp.status_code == 400

    def test_format_number_api(self, client):
        resp = client.post(
            "/locale/format/number",
            json={"value": 1234567.89, "decimal_places": 2},
        )
        assert resp.status_code == 200
        assert "1,234,567.89" in resp.get_json()["formatted"]

    def test_format_percent_api(self, client):
        resp = client.post(
            "/locale/format/percent", json={"value": 0.156}
        )
        assert resp.status_code == 200
        assert "15.6%" in resp.get_json()["formatted"]

    def test_format_date_api(self, client):
        resp = client.post(
            "/locale/format/date",
            json={"date": "2026-02-28T14:30:00", "format": "long", "locale": "zh_CN"},
        )
        assert resp.status_code == 200
        assert "2026" in resp.get_json()["formatted"]

    def test_format_date_missing(self, client):
        resp = client.post("/locale/format/date", json={})
        assert resp.status_code == 400
