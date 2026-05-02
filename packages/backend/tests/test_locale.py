from datetime import date, datetime

import pytest
from app import create_app
from app.config import Settings
from app.extensions import db
from app.models import User
from app.services.locale import LocaleFormatter, get_formatter


class TestLocaleFormatter:
  """Tests for LocaleFormatter class."""

  def test_format_currency_inr(self):
    fmt = LocaleFormatter("en-IN", "INR")
    result = fmt.format_currency(1234567.89)
    assert "₹" in result
    assert "12" in result

  def test_format_currency_usd(self):
    fmt = LocaleFormatter("en-US", "USD")
    result = fmt.format_currency(1234.56)
    assert "$" in result
    assert "1,234.56" in result

  def test_format_currency_eur_de(self):
    fmt = LocaleFormatter("de-DE", "EUR")
    result = fmt.format_currency(1234.56)
    assert "€" in result

  def test_format_currency_override(self):
    fmt = LocaleFormatter("en-US", "USD")
    result = fmt.format_currency(100.00, currency="GBP")
    assert "£" in result

  def test_format_number_en_us(self):
    fmt = LocaleFormatter("en-US")
    result = fmt.format_number(1234567.89)
    assert result == "1,234,567.89"

  def test_format_number_de_de(self):
    fmt = LocaleFormatter("de-DE")
    result = fmt.format_number(1234567.89)
    assert "1.234.567" in result

  def test_format_number_fr_fr(self):
    fmt = LocaleFormatter("fr-FR")
    result = fmt.format_number(1234.56)
    assert "1" in result
    assert "234" in result

  def test_format_date_en_us(self):
    fmt = LocaleFormatter("en-US")
    d = date(2024, 1, 15)
    result = fmt.format_date(d)
    assert "Jan" in result
    assert "2024" in result

  def test_format_date_de_de(self):
    fmt = LocaleFormatter("de-DE")
    d = date(2024, 1, 15)
    result = fmt.format_date(d)
    assert "2024" in result

  def test_format_datetime_en_us(self):
    fmt = LocaleFormatter("en-US")
    dt = datetime(2024, 1, 15, 14, 30, 0)
    result = fmt.format_datetime(dt)
    assert "2024" in result
    assert "Jan" in result

  def test_format_percent(self):
    fmt = LocaleFormatter("en-US")
    result = fmt.format_percent(0.856)
    assert "%" in result
    # 0.856 rounds to 86%
    assert "86" in result

  def test_to_dict_en_us(self):
    fmt = LocaleFormatter("en-US", "USD")
    info = fmt.to_dict()
    assert info["locale"] == "en-US"
    assert info["currency"] == "USD"
    assert info["currency_symbol"] == "$"
    assert info["decimal_symbol"] == "."
    assert info["grouping_symbol"] == ","
    assert "supported_locales" in info

  def test_to_dict_de_de(self):
    fmt = LocaleFormatter("de-DE", "EUR")
    info = fmt.to_dict()
    assert info["locale"] == "de-DE"
    assert info["currency"] == "EUR"
    assert info["currency_symbol"] == "€"

  def test_to_dict_inr(self):
    fmt = LocaleFormatter("en-IN", "INR")
    info = fmt.to_dict()
    assert info["currency_symbol"] == "₹"

  def test_supported_locales_not_empty(self):
    assert len(LocaleFormatter.SUPPORTED_LOCALES) > 0

  def test_currency_symbols_not_empty(self):
    assert len(LocaleFormatter.CURRENCY_SYMBOLS) > 0

  def test_format_currency_zero(self):
    fmt = LocaleFormatter("en-US", "USD")
    result = fmt.format_currency(0)
    assert "$" in result
    assert "0" in result

  def test_format_currency_large_amount(self):
    fmt = LocaleFormatter("en-US", "USD")
    result = fmt.format_currency(9999999.99)
    assert "$" in result
    assert "9,999,999.99" in result

  def test_format_number_small(self):
    fmt = LocaleFormatter("en-US")
    result = fmt.format_number(0.5)
    assert "0.5" in result

  def test_format_date_short(self):
    fmt = LocaleFormatter("en-US")
    d = date(2024, 12, 25)
    result = fmt.format_date(d, format="short")
    assert "24" in result


class TestGetFormatter:
  """Tests for get_formatter factory function."""

  def test_get_formatter_defaults(self, app_fixture):
    with app_fixture.app_context():
      fmt = get_formatter()
      assert fmt.locale_str == "en-US"
      assert fmt.currency == "INR"

  def test_get_formatter_custom(self, app_fixture):
    with app_fixture.app_context():
      fmt = get_formatter("de-DE", "EUR")
      assert fmt.locale_str == "de-DE"
      assert fmt.currency == "EUR"

  def test_get_formatter_partial_override(self, app_fixture):
    with app_fixture.app_context():
      fmt = get_formatter("fr-FR")
      assert fmt.locale_str == "fr-FR"
      assert fmt.currency == "INR"


class TestLocaleEndpoint:
  """Tests for /auth/locale and /auth/locale/options endpoints."""

  def test_get_locale_default(self, client, auth_header):
    """Locale endpoint should return default locale info."""
    response = client.get("/auth/locale", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"] == "en-US"
    assert data["currency"] == "INR"
    assert data["currency_symbol"] == "₹"
    assert "decimal_symbol" in data
    assert "grouping_symbol" in data
    assert "supported_locales" in data

  def test_get_locale_after_update(self, client, auth_header):
    """Locale endpoint should reflect user's locale preference."""
    client.patch(
      "/auth/me",
      json={"preferred_locale": "de-DE", "preferred_currency": "EUR"},
      headers=auth_header,
    )
    response = client.get("/auth/locale", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert data["locale"] == "de-DE"
    assert data["currency"] == "EUR"
    assert data["currency_symbol"] == "€"

  def test_get_locale_requires_auth(self, client):
    """Locale endpoint should require authentication."""
    response = client.get("/auth/locale")
    assert response.status_code == 401

  def test_get_locale_options(self, client, auth_header):
    """Options endpoint should return supported values."""
    response = client.get("/auth/locale/options", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert "locales" in data
    assert "currencies" in data
    assert "timezones" in data
    assert "en-US" in data["locales"]
    assert "USD" in data["currencies"]
    assert "UTC" in data["timezones"]


class TestUserLocaleUpdate:
  """Tests for updating user locale preferences via /auth/me."""

  def test_update_locale(self, client, auth_header):
    """Should update preferred_locale."""
    response = client.patch(
      "/auth/me",
      json={"preferred_locale": "fr-FR"},
      headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["preferred_locale"] == "fr-FR"

  def test_update_timezone(self, client, auth_header):
    """Should update preferred_timezone."""
    response = client.patch(
      "/auth/me",
      json={"preferred_timezone": "Asia/Kolkata"},
      headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["preferred_timezone"] == "Asia/Kolkata"

  def test_update_invalid_locale(self, client, auth_header):
    """Should reject unsupported locale."""
    response = client.patch(
      "/auth/me",
      json={"preferred_locale": "xx-XX"},
      headers=auth_header,
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "unsupported" in data["error"]

  def test_update_invalid_timezone(self, client, auth_header):
    """Should reject unsupported timezone."""
    response = client.patch(
      "/auth/me",
      json={"preferred_timezone": "Invalid/Zone"},
      headers=auth_header,
    )
    assert response.status_code == 400
    data = response.get_json()
    assert "unsupported" in data["error"]

  def test_me_returns_locale_fields(self, client, auth_header):
    """GET /auth/me should return locale and timezone fields."""
    response = client.get("/auth/me", headers=auth_header)
    assert response.status_code == 200
    data = response.get_json()
    assert "preferred_locale" in data
    assert "preferred_timezone" in data
    assert data["preferred_locale"] == "en-US"
    assert data["preferred_timezone"] == "UTC"

  def test_update_multiple_preferences(self, client, auth_header):
    """Should update currency, locale, and timezone together."""
    response = client.patch(
      "/auth/me",
      json={
        "preferred_currency": "EUR",
        "preferred_locale": "de-DE",
        "preferred_timezone": "Europe/Berlin",
      },
      headers=auth_header,
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["preferred_currency"] == "EUR"
    assert data["preferred_locale"] == "de-DE"
    assert data["preferred_timezone"] == "Europe/Berlin"
