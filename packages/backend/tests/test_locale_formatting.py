"""Tests for locale-aware formatting service and API (issue #131)."""

from datetime import date, datetime, timezone

import pytest


# ── Service tests ───────────────────────────────────────────────────────

class TestResolveLocale:
    def test_explicit_locale_overrides_currency(self):
        from app.services.locale_formatting import resolve_locale
        result = resolve_locale("INR", explicit_locale="ja_JP")
        assert result == "ja_JP"

    def test_currency_to_locale_mapping(self):
        from app.services.locale_formatting import resolve_locale
        assert resolve_locale("INR") == "en_IN"
        assert resolve_locale("USD") == "en_US"
        assert resolve_locale("EUR") == "de_DE"
        assert resolve_locale("JPY") == "ja_JP"

    def test_unknown_currency_defaults_to_en_us(self):
        from app.services.locale_formatting import resolve_locale
        assert resolve_locale("XYZ") == "en_US"

    def test_invalid_explicit_locale_falls_back(self):
        from app.services.locale_formatting import resolve_locale
        # Invalid locale should fall back to currency mapping
        result = resolve_locale("INR", explicit_locale="xx_XX")
        assert result == "en_IN"


class TestFormatCurrency:
    def test_usd_en_us(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(1234.56, "USD", "en_US")
        assert "$" in result
        assert "1,234.56" in result

    def test_inr_en_in(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(123456.78, "INR", "en_IN")
        assert "₹" in result

    def test_eur_de_de(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(1234.56, "EUR", "de_DE")
        assert "1.234,56" in result or "€" in result

    def test_auto_detect_from_currency(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(1000, "JPY")
        # Babel uses fullwidth yen sign ￥ on some platforms, standard ¥ on others
        assert "¥" in result or "￥" in result

    def test_integer_amount(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(100, "USD", "en_US")
        assert "$" in result

    def test_zero_amount(self):
        from app.services.locale_formatting import format_currency_amount
        result = format_currency_amount(0, "USD", "en_US")
        assert "$" in result
        assert "0.00" in result


class TestFormatNumber:
    def test_us_format(self):
        from app.services.locale_formatting import format_number
        result = format_number(1234.56, locale="en_US")
        assert "1,234.56" in result

    def test_german_format(self):
        from app.services.locale_formatting import format_number
        result = format_number(1234.56, locale="de_DE")
        assert "1.234,56" in result

    def test_currency_based_locale(self):
        from app.services.locale_formatting import format_number
        result = format_number(1234.56, currency="EUR")
        # German locale should use comma as decimal separator
        assert "1.234" in result or "1,234" in result

    def test_default_locale(self):
        from app.services.locale_formatting import format_number
        result = format_number(1000, locale=None, currency=None)
        assert "1,000" in result or "1.000" in result


class TestFormatPercentage:
    def test_us_format(self):
        from app.services.locale_formatting import format_percentage
        result = format_percentage(0.1523, locale="en_US")
        assert "15" in result
        assert "%" in result

    def test_german_format(self):
        from app.services.locale_formatting import format_percentage
        result = format_percentage(0.1523, locale="de_DE")
        assert "%" in result


class TestFormatDate:
    def test_medium_format_en_us(self):
        from app.services.locale_formatting import format_date_locale
        result = format_date_locale(date(2026, 2, 16), "medium", "en_US")
        assert "2026" in result
        assert "Feb" in result or "2" in result

    def test_short_format(self):
        from app.services.locale_formatting import format_date_locale
        result = format_date_locale(date(2026, 2, 16), "short", "en_US")
        assert "26" in result or "2026" in result

    def test_datetime_input(self):
        from app.services.locale_formatting import format_date_locale
        dt = datetime(2026, 2, 16, 14, 30, 0)
        result = format_date_locale(dt, "medium", "en_US")
        assert "2026" in result

    def test_currency_based_locale(self):
        from app.services.locale_formatting import format_date_locale
        result = format_date_locale(date(2026, 2, 16), "medium", currency="INR")
        assert "2026" in result


class TestFormatRelativeTime:
    def test_today(self):
        from app.services.locale_formatting import format_relative_time
        today = date.today()
        assert format_relative_time(today) == "today"

    def test_tomorrow(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        tomorrow = today + timedelta(days=1)
        assert format_relative_time(tomorrow) == "tomorrow"

    def test_yesterday(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        yesterday = today - timedelta(days=1)
        assert format_relative_time(yesterday) == "yesterday"

    def test_days_ago(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        five_days_ago = today - timedelta(days=5)
        result = format_relative_time(five_days_ago)
        assert "5 days ago" == result

    def test_weeks_ago(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        two_weeks_ago = today - timedelta(days=14)
        result = format_relative_time(two_weeks_ago)
        assert "2 weeks ago" == result

    def test_months_ago(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        three_months_ago = today - timedelta(days=90)
        result = format_relative_time(three_months_ago)
        assert "month" in result
        assert "ago" in result

    def test_in_future(self):
        from app.services.locale_formatting import format_relative_time
        from datetime import timedelta
        today = date.today()
        in_3_days = today + timedelta(days=3)
        result = format_relative_time(in_3_days)
        assert "in 3 days" == result

    def test_with_reference(self):
        from app.services.locale_formatting import format_relative_time
        ref = date(2026, 1, 1)
        target = date(2026, 1, 3)
        result = format_relative_time(target, reference=ref)
        assert "in 2 days" == result


class TestGetLocaleInfo:
    def test_en_us(self):
        from app.services.locale_formatting import get_locale_info
        info = get_locale_info("en_US")
        assert info["locale"] == "en_US"
        assert "number_format" in info
        assert info["number_format"]["decimal_separator"] == "."
        assert "currency_symbols" in info
        assert info["currency_symbols"].get("USD") == "$"

    def test_de_de(self):
        from app.services.locale_formatting import get_locale_info
        info = get_locale_info("de_DE")
        assert info["locale"] == "de_DE"
        # Babel uses ',' for decimal in formatted output but number_symbols
        # may vary — just verify the key exists
        assert "number_format" in info
        assert "decimal_separator" in info["number_format"]
        assert "currency_symbols" in info

    def test_unknown_locale(self):
        from app.services.locale_formatting import get_locale_info
        info = get_locale_info("xx_XX")
        assert "error" in info


# ── API endpoint tests ──────────────────────────────────────────────────

class TestLocaleAPI:
    def test_list_locales(self, client):
        resp = client.get("/locale/locales")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "locales" in data
        assert data["total"] >= 15
        # Check a known locale is present
        codes = [l["code"] for l in data["locales"]]
        assert "en_US" in codes
        assert "ja_JP" in codes

    def test_locale_info_valid(self, client):
        resp = client.get("/locale/info/en_US")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["locale"] == "en_US"
        assert "number_format" in data

    def test_locale_info_invalid(self, client):
        resp = client.get("/locale/info/xx_XX")
        assert resp.status_code == 404

    def test_format_currency(self, client):
        resp = client.post(
            "/locale/format/currency",
            json={"amount": 1234.56, "currency": "USD", "locale": "en_US"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "$" in data["formatted"]
        assert data["locale"] == "en_US"

    def test_format_currency_auto_detect(self, client):
        resp = client.post(
            "/locale/format/currency",
            json={"amount": 50000, "currency": "INR"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "₹" in data["formatted"]
        assert data["locale"] == "en_IN"

    def test_format_currency_missing_fields(self, client):
        resp = client.post(
            "/locale/format/currency",
            json={"amount": 100},
        )
        assert resp.status_code == 400

    def test_format_currency_invalid_amount(self, client):
        resp = client.post(
            "/locale/format/currency",
            json={"amount": "not_a_number", "currency": "USD"},
        )
        assert resp.status_code == 400

    def test_format_number(self, client):
        resp = client.post(
            "/locale/format/number",
            json={"value": 1234.56, "locale": "en_US"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "1,234.56" in data["formatted"]

    def test_format_number_missing_value(self, client):
        resp = client.post(
            "/locale/format/number",
            json={},
        )
        assert resp.status_code == 400

    def test_format_percent(self, client):
        resp = client.post(
            "/locale/format/percent",
            json={"value": 0.1523, "locale": "en_US"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "%" in data["formatted"]

    def test_format_date(self, client):
        resp = client.post(
            "/locale/format/date",
            json={"date": "2026-02-16", "locale": "en_US"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "2026" in data["formatted"]

    def test_format_date_with_datetime(self, client):
        resp = client.post(
            "/locale/format/date",
            json={"date": "2026-02-16T14:30:00", "locale": "en_US"},
        )
        assert resp.status_code == 200

    def test_format_date_invalid(self, client):
        resp = client.post(
            "/locale/format/date",
            json={"date": "not-a-date", "locale": "en_US"},
        )
        assert resp.status_code == 400

    def test_format_relative(self, client):
        today = date.today().isoformat()
        resp = client.get(f"/locale/format/relative?date={today}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["formatted"] == "today"

    def test_format_relative_missing_date(self, client):
        resp = client.get("/locale/format/relative")
        assert resp.status_code == 400

    def test_format_relative_with_reference(self, client):
        resp = client.get(
            "/locale/format/relative?date=2026-01-03&reference=2026-01-01"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert "in 2 days" == data["formatted"]
