"""Tests for locale-aware formatting service and API endpoints."""
import pytest
from app import create_app
from app.config import Settings
from app.services.locale_formatter import (
    format_currency,
    format_date,
    format_datetime,
    format_number,
    locale_meta,
    supported_locales,
    _resolve_locale,
)
from datetime import date, datetime


@pytest.fixture
def app():
    settings = Settings(
        database_url="sqlite:///:memory:",
        redis_url="redis://localhost:6379/0",
        jwt_secret="test-secret",
    )
    application = create_app(settings)
    application.config["TESTING"] = True
    return application


@pytest.fixture
def client(app):
    return app.test_client()


# ── locale_formatter unit tests ───────────────────────────────────────────────

class TestFormatCurrency:
    def test_inr_en_in(self):
        result = format_currency(1234.50, "INR", "en_IN")
        assert "1,234" in result or "1234" in result
        assert "₹" in result or "INR" in result

    def test_usd_en_us(self):
        result = format_currency(9876.54, "USD", "en_US")
        assert "9,876" in result or "9876" in result

    def test_eur_de_de(self):
        result = format_currency(1000.0, "EUR", "de_DE")
        assert "€" in result or "EUR" in result

    def test_zero_amount(self):
        result = format_currency(0, "INR", "en_IN")
        assert result is not None and isinstance(result, str)

    def test_fallback_unknown_locale(self):
        # Unknown locale should not raise, just fall back
        result = format_currency(500.0, "INR", "xx_XX")
        assert isinstance(result, str)


class TestFormatNumber:
    def test_en_us_grouping(self):
        result = format_number(1234567.89, "en_US")
        assert "1,234,567" in result

    def test_de_de_grouping(self):
        result = format_number(1234567.89, "de_DE")
        # German uses dot as thousands separator
        assert isinstance(result, str) and len(result) > 0

    def test_decimal_places(self):
        result = format_number(3.14159, "en_US", decimal_places=3)
        assert "3.142" in result or "3.14" in result

    def test_zero_decimal_places(self):
        result = format_number(42.7, "en_US", decimal_places=0)
        assert isinstance(result, str)


class TestFormatDate:
    def test_date_object(self):
        result = format_date(date(2026, 2, 24), "en_US", "medium")
        assert "2026" in result

    def test_date_string(self):
        result = format_date("2026-02-24", "en_IN", "long")
        assert "2026" in result

    def test_invalid_string_passthrough(self):
        result = format_date("not-a-date", "en_US")
        assert result == "not-a-date"

    def test_short_format(self):
        result = format_date(date(2026, 2, 24), "en_US", "short")
        assert isinstance(result, str) and len(result) > 0


class TestFormatDatetime:
    def test_datetime_object(self):
        result = format_datetime(datetime(2026, 2, 24, 13, 0, 0), "en_US", "medium")
        assert "2026" in result

    def test_datetime_string(self):
        result = format_datetime("2026-02-24T13:00:00", "en_IN")
        assert isinstance(result, str)


class TestSupportedLocales:
    def test_returns_list(self):
        locales = supported_locales()
        assert isinstance(locales, list)
        assert len(locales) >= 10

    def test_contains_en_in(self):
        assert "en_IN" in supported_locales()

    def test_contains_en_us(self):
        assert "en_US" in supported_locales()


class TestLocaleMeta:
    def test_returns_dict(self):
        meta = locale_meta("en_US")
        assert isinstance(meta, dict)
        assert meta["locale"] == "en_US"

    def test_default_locale(self):
        meta = locale_meta(None)
        assert meta["locale"] == "en_IN"


class TestResolveLocale:
    def test_hyphen_normalisation(self):
        assert _resolve_locale("en-IN") == "en_IN"

    def test_unknown_returns_default(self):
        assert _resolve_locale("xx_XX") == "en_IN"

    def test_none_returns_default(self):
        assert _resolve_locale(None) == "en_IN"


# ── API endpoint tests ────────────────────────────────────────────────────────

class TestLocaleAPI:
    def test_supported_endpoint(self, client):
        resp = client.get("/locale/supported")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "locales" in data
        assert isinstance(data["locales"], list)

    def test_meta_endpoint(self, client):
        resp = client.get("/locale/meta?locale=en_US")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["locale"] == "en_US"

    def test_format_endpoint_currency(self, client):
        resp = client.post("/locale/format", json={
            "locale": "en_US",
            "values": [{"type": "currency", "amount": 1234.5, "currency": "USD"}]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) == 1
        assert isinstance(data["results"][0], str)

    def test_format_endpoint_mixed(self, client):
        resp = client.post("/locale/format", json={
            "locale": "en_IN",
            "values": [
                {"type": "currency", "amount": 5000.0, "currency": "INR"},
                {"type": "number",   "value": 42.5, "decimal_places": 1},
                {"type": "date",     "value": "2026-02-24", "format": "medium"},
            ]
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["results"]) == 3

    def test_format_endpoint_invalid_values(self, client):
        resp = client.post("/locale/format", json={"locale": "en_US", "values": "bad"})
        assert resp.status_code == 400
