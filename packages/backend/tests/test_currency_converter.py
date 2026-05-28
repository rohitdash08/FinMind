"""Tests for Currency Converter."""

import pytest


class TestCurrencyConverter:
    def test_basic_conversion(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        result = svc.convert(100, "USD", "EUR")
        assert result["from"]["amount"] == 100
        assert result["to"]["amount"] > 0
        assert result["rate"] > 0

    def test_inverse_conversion(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        r1 = svc.convert(100, "USD", "EUR")
        r2 = svc.convert(r1["to"]["amount"], "EUR", "USD")
        assert abs(r2["to"]["amount"] - 100) < 0.1

    def test_same_currency(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        result = svc.convert(100, "USD", "USD")
        assert result["to"]["amount"] == 100

    def test_batch_convert(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        txs = [
            {"amount": 100, "currency": "EUR"},
            {"amount": 5000, "currency": "JPY"},
            {"amount": 50, "currency": "GBP"},
        ]
        result = svc.batch_convert(txs, "USD")
        assert result["success_count"] == 3
        assert result["total_converted"] > 0

    def test_unsupported_currency(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        result = svc.convert(100, "USD", "XYZ")
        assert "error" in result

    def test_favorites(self):
        from app.services.currency_converter import CurrencyConverter
        svc = CurrencyConverter()
        svc.add_favorite("user1", "USD", "CNY")
        favs = svc.get_favorites("user1")
        assert len(favs) == 1
        assert favs[0]["from"] == "USD"
