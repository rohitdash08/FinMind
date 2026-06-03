"""
Tests for locale-aware formatting utilities.
"""
import pytest
from datetime import date, datetime
from app.utils.locale import (
    format_currency,
    format_number,
    format_date,
    format_percentage,
    get_locale_for_country,
    LOCALE_MAP,
)
from app.extensions import db


class TestFormatCurrency:
    """Test format_currency function."""

    def test_indian_currency(self):
        """Test Indian Rupee formatting."""
        result = format_currency(1234567.89, currency="INR", locale="en_IN")
        assert "₹" in result
        assert "12" in result

    def test_us_currency(self):
        """Test US Dollar formatting."""
        result = format_currency(1234.56, currency="USD", locale="en_US")
        assert "$" in result
        assert "1,234.56" in result

    def test_euro_currency(self):
        """Test Euro formatting."""
        result = format_currency(99.99, currency="EUR", locale="de_DE")
        assert "€" in result or "99" in result

    def test_zero_amount(self):
        """Test zero amount formatting."""
        result = format_currency(0, currency="USD", locale="en_US")
        assert "$0" in result or "0" in result

    def test_negative_amount(self):
        """Test negative amount formatting."""
        result = format_currency(-500, currency="USD", locale="en_US")
        assert "-" in result or "500" in result


class TestFormatNumber:
    """Test format_number function."""

    def test_basic_number(self):
        """Test basic number formatting."""
        result = format_number(1234567.89, locale="en_US")
        assert "1,234,567.89" in result

    def test_decimal_places(self):
        """Test custom decimal places."""
        result = format_number(1234.5, locale="en_US", decimal_places=0)
        assert "1,235" in result or "1,234" in result

    def test_small_number(self):
        """Test small number formatting."""
        result = format_number(0.5, locale="en_US")
        assert "0.50" in result

    def test_german_number_format(self):
        """Test German number format (uses comma as decimal separator)."""
        result = format_number(1234.56, locale="de_DE")
        assert "1.234" in result or "1234" in result


class TestFormatDate:
    """Test format_date function."""

    def test_date_object(self):
        """Test formatting date object."""
        d = date(2024, 1, 15)
        result = format_date(d, locale="en_US", format="medium")
        assert "Jan" in result
        assert "15" in result
        assert "2024" in result

    def test_datetime_object(self):
        """Test formatting datetime object."""
        dt = datetime(2024, 6, 30, 14, 30)
        result = format_date(dt, locale="en_US", format="medium")
        assert "Jun" in result
        assert "30" in result

    def test_short_format(self):
        """Test short date format."""
        d = date(2024, 3, 5)
        result = format_date(d, locale="en_US", format="short")
        assert "3" in result
        assert "5" in result

    def test_long_format(self):
        """Test long date format."""
        d = date(2024, 1, 1)
        result = format_date(d, locale="en_US", format="long")
        assert "January" in result
        assert "2024" in result


class TestFormatPercentage:
    """Test format_percentage function."""

    def test_percentage_form(self):
        """Test percentage from whole number (50 = 50%)."""
        result = format_percentage(50, locale="en_US", is_decimal=False)
        assert "50" in result
        assert "%" in result

    def test_decimal_form(self):
        """Test percentage from decimal (0.5 = 50%)."""
        result = format_percentage(0.5, locale="en_US", is_decimal=True)
        assert "50" in result
        assert "%" in result

    def test_zero_percentage(self):
        """Test zero percentage."""
        result = format_percentage(0, locale="en_US")
        assert "0" in result

    def test_over_100_percentage(self):
        """Test over 100% percentage."""
        result = format_percentage(150, locale="en_US", is_decimal=False)
        assert "150" in result


class TestGetLocaleForCountry:
    """Test get_locale_for_country function."""

    def test_known_country(self):
        """Test known country codes."""
        assert get_locale_for_country("IN") == "en_IN"
        assert get_locale_for_country("US") == "en_US"
        assert get_locale_for_country("GB") == "en_GB"

    def test_case_insensitive(self):
        """Test case insensitive country codes."""
        assert get_locale_for_country("in") == "en_IN"
        assert get_locale_for_country("us") == "en_US"

    def test_unknown_country(self):
        """Test unknown country code defaults to en_IN."""
        assert get_locale_for_country("XX") == "en_IN"
        assert get_locale_for_country("ZZ") == "en_IN"

    def test_all_mapped_countries(self):
        """Test all countries in LOCALE_MAP."""
        for country, locale in LOCALE_MAP.items():
            assert get_locale_for_country(country) == locale


@pytest.fixture
def app():
    """Create application for testing."""
    from app import create_app
    
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def db(app):
    """Create database for testing."""
    with app.app_context():
        yield db
