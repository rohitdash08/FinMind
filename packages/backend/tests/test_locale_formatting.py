"""Tests for locale-aware formatting service and routes."""

import pytest
from datetime import date, datetime, timedelta
from decimal import Decimal

from app.services.locale_formatting import (
    format_number,
    format_currency,
    format_date,
    format_datetime,
    format_percentage,
    format_compact_number,
    format_expense_for_locale,
    format_bill_for_locale,
    get_available_locales,
    get_supported_currencies,
    get_formatting_preview,
    get_user_locale_preferences,
    update_user_locale_preferences,
    LOCALE_CONFIG,
    CURRENCY_SYMBOLS,
    COMMON_TIMEZONES,
)


# ─── Number Formatting Tests ────────────────────────────────────────


class TestFormatNumber:
    def test_basic_en_us(self):
        assert format_number(1234.56, "en_US") == "1,234.56"

    def test_basic_de_de(self):
        assert format_number(1234.56, "de_DE") == "1.234,56"

    def test_basic_fr_fr(self):
        result = format_number(1234.56, "fr_FR")
        assert "1" in result and "234" in result and "56" in result

    def test_large_number(self):
        assert format_number(1234567.89, "en_US") == "1,234,567.89"

    def test_small_number(self):
        assert format_number(0.99, "en_US") == "0.99"

    def test_zero(self):
        assert format_number(0, "en_US") == "0.00"

    def test_negative(self):
        assert format_number(-1234.56, "en_US") == "-1,234.56"

    def test_decimal_input(self):
        assert format_number(Decimal("1234.56"), "en_US") == "1,234.56"

    def test_integer_input(self):
        assert format_number(1000, "en_US", decimal_places=0) == "1,000"

    def test_no_grouping(self):
        assert format_number(1234567, "en_US", decimal_places=0, use_grouping=False) == "1234567"

    def test_custom_decimal_places(self):
        assert format_number(1234.5678, "en_US", decimal_places=3) == "1,234.568"

    def test_unknown_locale_fallback(self):
        # Should fall back to en_US
        assert format_number(1234.56, "xx_XX") == "1,234.56"

    def test_japanese_locale(self):
        assert format_number(1234.56, "ja_JP") == "1,234.56"

    def test_spanish_locale(self):
        assert format_number(1234.56, "es_ES") == "1.234,56"


class TestFormatPercentage:
    def test_basic(self):
        assert format_percentage(85.5, "en_US") == "85.5%"

    def test_german(self):
        assert format_percentage(85.5, "de_DE") == "85,5%"

    def test_zero_decimal(self):
        assert format_percentage(100, "en_US", decimal_places=0) == "100%"


class TestFormatCompactNumber:
    def test_thousands(self):
        result = format_compact_number(1500, "en_US")
        assert "1" in result and "5" in result and "K" in result

    def test_millions(self):
        result = format_compact_number(2500000, "en_US")
        assert "2" in result and "5" in result and "M" in result

    def test_billions(self):
        result = format_compact_number(3500000000, "en_US")
        assert "3" in result and "5" in result and "B" in result

    def test_small_number(self):
        result = format_compact_number(500, "en_US")
        assert "500" in result

    def test_negative(self):
        result = format_compact_number(-1500, "en_US")
        assert "-" in result and "K" in result


# ─── Currency Formatting Tests ──────────────────────────────────────


class TestFormatCurrency:
    def test_usd(self):
        assert format_currency(1234.56, "USD", "en_US") == "$1,234.56"

    def test_eur_german(self):
        result = format_currency(1234.56, "EUR", "de_DE")
        assert "€" in result and "1.234" in result

    def test_gbp(self):
        assert format_currency(99.99, "GBP", "en_GB") == "£99.99"

    def test_jpy_no_decimals(self):
        result = format_currency(10000, "JPY", "ja_JP")
        assert "¥" in result and "10,000" in result

    def test_inr(self):
        result = format_currency(500, "INR", "en_US")
        assert "₹" in result and "500" in result

    def test_code_display(self):
        result = format_currency(100, "USD", "en_US", display="code")
        assert "USD" in result

    def test_name_display(self):
        result = format_currency(100, "USD", "en_US", display="name")
        assert "US Dollar" in result

    def test_compact_mode(self):
        result = format_currency(1500000, "USD", "en_US", compact=True)
        assert "$" in result and "M" in result

    def test_unknown_currency_fallback(self):
        result = format_currency(100, "XYZ", "en_US")
        assert "XYZ" in result


# ─── Date Formatting Tests ──────────────────────────────────────────


class TestFormatDate:
    def test_en_us_medium(self):
        d = date(2026, 3, 15)
        result = format_date(d, "en_US", "medium")
        assert "Mar" in result and "15" in result

    def test_en_us_short(self):
        d = date(2026, 3, 15)
        result = format_date(d, "en_US", "short")
        assert "03/15/2026" == result

    def test_en_gb_short(self):
        d = date(2026, 3, 15)
        result = format_date(d, "en_GB", "short")
        assert "15/03/2026" == result

    def test_de_de_short(self):
        d = date(2026, 3, 15)
        result = format_date(d, "de_DE", "short")
        assert "15.03.2026" == result

    def test_iso_format(self):
        d = date(2026, 3, 15)
        assert format_date(d, "en_US", "iso") == "2026-03-15"

    def test_string_input(self):
        result = format_date("2026-03-15", "en_US", "short")
        assert "03/15/2026" == result

    def test_datetime_input(self):
        dt = datetime(2026, 3, 15, 10, 30)
        result = format_date(dt, "en_US", "short")
        assert "03/15/2026" == result

    def test_relative_today(self):
        result = format_date(date.today(), "en_US", relative=True)
        assert result == "Today"

    def test_relative_yesterday(self):
        yesterday = date.today() - timedelta(days=1)
        result = format_date(yesterday, "en_US", relative=True)
        assert result == "Yesterday"

    def test_relative_tomorrow(self):
        tomorrow = date.today() + timedelta(days=1)
        result = format_date(tomorrow, "en_US", relative=True)
        assert result == "Tomorrow"

    def test_relative_days_ago(self):
        three_days_ago = date.today() - timedelta(days=3)
        result = format_date(three_days_ago, "en_US", relative=True)
        assert "3 days ago" == result

    def test_relative_german(self):
        result = format_date(date.today(), "de_DE", relative=True)
        assert result == "Heute"

    def test_relative_japanese(self):
        result = format_date(date.today(), "ja_JP", relative=True)
        assert result == "今日"

    def test_invalid_string(self):
        result = format_date("not-a-date", "en_US")
        assert result == "not-a-date"


class TestFormatDatetime:
    def test_with_time(self):
        dt = datetime(2026, 3, 15, 14, 30)
        result = format_datetime(dt, "en_US", "medium")
        assert "14:30" in result

    def test_without_time(self):
        dt = datetime(2026, 3, 15, 14, 30)
        result = format_datetime(dt, "en_US", "medium", include_time=False)
        assert "14:30" not in result

    def test_string_input(self):
        result = format_datetime("2026-03-15T14:30:00", "en_US")
        assert "14:30" in result


# ─── Expense/Bill Formatting Tests ──────────────────────────────────


class TestFormatExpenseForLocale:
    def test_formats_amount_and_date(self):
        expense = {"amount": 1234.56, "currency": "USD", "spent_at": "2026-03-15"}
        result = format_expense_for_locale(expense, "en_US")
        assert "amount_formatted" in result
        assert "$" in result["amount_formatted"]
        assert "spent_at_formatted" in result

    def test_german_locale(self):
        expense = {"amount": 1234.56, "currency": "EUR", "spent_at": "2026-03-15"}
        result = format_expense_for_locale(expense, "de_DE")
        assert "€" in result["amount_formatted"]


class TestFormatBillForLocale:
    def test_formats_bill(self):
        bill = {"amount": 500, "currency": "INR", "next_due_date": str(date.today())}
        result = format_bill_for_locale(bill, "en_US")
        assert "amount_formatted" in result
        assert "next_due_date_formatted" in result
        assert result["next_due_date_formatted"] == "Today"


# ─── Registry Tests ─────────────────────────────────────────────────


class TestLocaleRegistry:
    def test_available_locales(self):
        locales = get_available_locales()
        assert len(locales) >= 10
        codes = [l["code"] for l in locales]
        assert "en_US" in codes
        assert "de_DE" in codes
        assert "ja_JP" in codes

    def test_locale_has_samples(self):
        locales = get_available_locales()
        for loc in locales:
            assert "sample_number" in loc
            assert "sample_date" in loc

    def test_supported_currencies(self):
        currencies = get_supported_currencies()
        assert len(currencies) >= 20
        codes = [c["code"] for c in currencies]
        assert "USD" in codes
        assert "EUR" in codes
        assert "INR" in codes

    def test_currency_has_samples(self):
        currencies = get_supported_currencies()
        for c in currencies:
            assert "sample" in c
            assert "symbol" in c

    def test_common_timezones(self):
        assert "UTC" in COMMON_TIMEZONES
        assert "America/New_York" in COMMON_TIMEZONES
        assert len(COMMON_TIMEZONES) >= 20


class TestFormattingPreview:
    def test_preview_en_us(self):
        preview = get_formatting_preview("en_US", "USD")
        assert preview["locale"] == "en_US"
        assert "samples" in preview
        samples = preview["samples"]
        assert "number" in samples
        assert "currency_small" in samples
        assert "date_short" in samples

    def test_preview_de_de(self):
        preview = get_formatting_preview("de_DE", "EUR")
        assert preview["locale"] == "de_DE"


# ─── User Preferences Tests (Database) ──────────────────────────────


class TestUserPreferences:
    def test_get_default_preferences(self, app_fixture):
        """Non-existent user returns defaults."""
        with app_fixture.app_context():
            prefs = get_user_locale_preferences(99999)
            assert prefs["locale"] == "en_US"
            assert prefs["timezone"] == "UTC"

    def test_get_preferences(self, client, auth_header):
        resp = client.get("/locale/preferences", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "locale" in data
        assert "timezone" in data

    def test_update_preferences(self, client, auth_header):
        resp = client.put("/locale/preferences", headers=auth_header,
                          json={"locale": "de_DE", "timezone": "Europe/Berlin"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["locale"] == "de_DE"
        assert data["timezone"] == "Europe/Berlin"

    def test_update_invalid_locale_ignored(self, client, auth_header):
        resp = client.put("/locale/preferences", headers=auth_header,
                          json={"locale": "invalid_XX"})
        assert resp.status_code == 200
        data = resp.get_json()
        # Should remain default since invalid locale is ignored
        assert data["locale"] in LOCALE_CONFIG

    def test_update_empty_body(self, client, auth_header):
        resp = client.put("/locale/preferences", headers=auth_header, json={})
        assert resp.status_code == 400

    def test_update_currency_display(self, client, auth_header):
        resp = client.put("/locale/preferences", headers=auth_header,
                          json={"currency_display": "code"})
        assert resp.status_code == 200
        assert resp.get_json()["currency_display"] == "code"


# ─── Route Tests ────────────────────────────────────────────────────


class TestLocaleRoutes:
    def test_list_locales(self, client, auth_header):
        resp = client.get("/locale/locales", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "locales" in data
        assert data["count"] >= 10

    def test_list_currencies(self, client, auth_header):
        resp = client.get("/locale/currencies", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "currencies" in data
        assert data["count"] >= 20

    def test_list_timezones(self, client, auth_header):
        resp = client.get("/locale/timezones", headers=auth_header)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "timezones" in data
        assert "UTC" in data["timezones"]

    def test_preview_formatting(self, client, auth_header):
        resp = client.post("/locale/preview", headers=auth_header,
                           json={"locale": "de_DE", "currency": "EUR"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["locale"] == "de_DE"
        assert "samples" in data

    def test_format_number(self, client, auth_header):
        resp = client.post("/locale/format/number", headers=auth_header,
                           json={"value": 1234.56, "locale": "en_US"})
        assert resp.status_code == 200
        assert resp.get_json()["formatted"] == "1,234.56"

    def test_format_number_missing_value(self, client, auth_header):
        resp = client.post("/locale/format/number", headers=auth_header, json={})
        assert resp.status_code == 400

    def test_format_currency_route(self, client, auth_header):
        resp = client.post("/locale/format/currency", headers=auth_header,
                           json={"amount": 99.99, "currency": "USD", "locale": "en_US"})
        assert resp.status_code == 200
        assert "$" in resp.get_json()["formatted"]

    def test_format_currency_missing_amount(self, client, auth_header):
        resp = client.post("/locale/format/currency", headers=auth_header, json={})
        assert resp.status_code == 400

    def test_format_date_route(self, client, auth_header):
        resp = client.post("/locale/format/date", headers=auth_header,
                           json={"date": "2026-03-15", "locale": "en_US", "style": "short"})
        assert resp.status_code == 200
        assert resp.get_json()["formatted"] == "03/15/2026"

    def test_format_date_missing(self, client, auth_header):
        resp = client.post("/locale/format/date", headers=auth_header, json={})
        assert resp.status_code == 400

    def test_format_date_relative(self, client, auth_header):
        today = date.today().isoformat()
        resp = client.post("/locale/format/date", headers=auth_header,
                           json={"date": today, "locale": "en_US", "relative": True})
        assert resp.status_code == 200
        assert resp.get_json()["formatted"] == "Today"
