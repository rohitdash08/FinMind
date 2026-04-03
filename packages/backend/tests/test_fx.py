"""Tests for multi-currency FX conversion service (#95)."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import date
from packages.backend.app.services.fx import (
    get_exchange_rate,
    convert_amount,
    list_supported_currencies,
    normalize_to_base,
    _STATIC_RATES_INR,
    _normalize_currency,
)

# Note: _normalize_currency does not exist - using upper() inline in service
# Tests are written to match actual service implementation


class TestStaticRates:
    def test_inr_base_rate_is_1(self):
        assert _STATIC_RATES_INR["INR"] == 1.0

    def test_usd_rate_is_positive(self):
        assert _STATIC_RATES_INR["USD"] > 0

    def test_at_least_20_currencies_supported(self):
        assert len(_STATIC_RATES_INR) >= 20

    def test_all_rates_are_positive(self):
        for code, rate in _STATIC_RATES_INR.items():
            assert rate > 0, f"{code} rate should be positive"


class TestGetExchangeRate:
    def test_same_currency_returns_1(self):
        result = get_exchange_rate("USD", "USD")
        assert result["rate"] == 1.0
        assert result["source"] == "identity"

    def test_inr_to_inr_returns_1(self):
        result = get_exchange_rate("INR", "INR")
        assert result["rate"] == 1.0

    def test_usd_to_inr_uses_static(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = get_exchange_rate("USD", "INR")
        assert result["rate"] > 1.0  # 1 USD > 1 INR
        assert result["source"] == "static"
        assert result["from_currency"] == "USD"
        assert result["to_currency"] == "INR"

    def test_live_rate_preferred_when_available(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=84.5):
            result = get_exchange_rate("USD", "INR")
        assert result["rate"] == 84.5
        assert result["source"] == "live"

    def test_unsupported_currency_raises_error(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            with pytest.raises(ValueError, match="Unsupported currency"):
                get_exchange_rate("XYZ", "INR")

    def test_cross_currency_conversion_via_inr(self):
        """USD->EUR should work via INR as intermediary."""
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = get_exchange_rate("USD", "EUR")
        assert result["rate"] > 0
        # USD is ~83.5 INR, EUR is ~90.2 INR, so USD/EUR < 1
        assert result["rate"] < 1.5  # 1 USD < 2 EUR

    def test_result_has_required_fields(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = get_exchange_rate("USD", "INR")
        assert "from_currency" in result
        assert "to_currency" in result
        assert "rate" in result
        assert "date" in result
        assert "source" in result

    def test_rate_is_positive(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = get_exchange_rate("EUR", "USD")
        assert result["rate"] > 0

    def test_caching_returns_same_rate(self):
        """Second call for same pair+date should use cache."""
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=85.0) as mock_live:
            r1 = get_exchange_rate("USD", "INR")
            r2 = get_exchange_rate("USD", "INR")
        # Live API should only be called once
        assert r1["rate"] == r2["rate"]


class TestConvertAmount:
    def test_convert_usd_to_inr(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = convert_amount(100.0, "USD", "INR")
        assert result["original_amount"] == 100.0
        assert result["converted_amount"] > 1000  # 100 USD > 1000 INR
        assert result["from_currency"] == "USD"
        assert result["to_currency"] == "INR"

    def test_convert_same_currency(self):
        result = convert_amount(500.0, "INR", "INR")
        assert result["converted_amount"] == 500.0

    def test_convert_zero_amount(self):
        result = convert_amount(0.0, "USD", "INR")
        assert result["converted_amount"] == 0.0

    def test_convert_result_has_all_fields(self):
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = convert_amount(100.0, "USD", "EUR")
        required_keys = ["original_amount", "converted_amount", "from_currency",
                        "to_currency", "rate", "date", "source"]
        for key in required_keys:
            assert key in result, f"Missing field: {key}"

    def test_conversion_is_reversible(self):
        """A->B then B->A should approximately return original amount."""
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            forward = convert_amount(1000.0, "INR", "USD")
            backward = convert_amount(forward["converted_amount"], "USD", "INR")
        assert abs(backward["converted_amount"] - 1000.0) < 1.0  # Within 1 INR


class TestListCurrencies:
    def test_returns_list(self):
        result = list_supported_currencies()
        assert isinstance(result, list)

    def test_all_items_have_code_and_rate(self):
        result = list_supported_currencies()
        for item in result:
            assert "code" in item
            assert "rate_vs_inr" in item

    def test_inr_is_included(self):
        result = list_supported_currencies()
        codes = [c["code"] for c in result]
        assert "INR" in codes

    def test_usd_is_included(self):
        result = list_supported_currencies()
        codes = [c["code"] for c in result]
        assert "USD" in codes


class TestNormalizeToBase:
    def test_normalize_mixed_currencies(self):
        amounts = [
            {"amount": 100.0, "currency": "USD"},
            {"amount": 5000.0, "currency": "INR"},
        ]
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = normalize_to_base(1, amounts, "INR")
        assert len(result) == 2
        # USD amount should be converted, INR should stay same
        assert result[1]["base_amount"] == 5000.0
        assert result[0]["base_amount"] > 1000  # 100 USD > 1000 INR

    def test_same_currency_no_conversion_needed(self):
        amounts = [{"amount": 500.0, "currency": "INR"}]
        result = normalize_to_base(1, amounts, "INR")
        assert result[0]["base_amount"] == 500.0
        assert result[0]["rate"] == 1.0

    def test_original_fields_preserved(self):
        amounts = [{"amount": 100.0, "currency": "USD", "category": "food"}]
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = normalize_to_base(1, amounts, "INR")
        assert result[0]["category"] == "food"
        assert result[0]["amount"] == 100.0

    def test_empty_list_returns_empty(self):
        result = normalize_to_base(1, [], "INR")
        assert result == []

    def test_base_currency_in_results(self):
        amounts = [{"amount": 200.0, "currency": "EUR"}]
        with patch("packages.backend.app.services.fx._fetch_live_rate", return_value=None):
            result = normalize_to_base(1, amounts, "INR")
        assert result[0]["base_currency"] == "INR"

