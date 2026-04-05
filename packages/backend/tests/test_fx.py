"""Tests for multi-currency FX (issue #95)."""
import pytest
from unittest.mock import MagicMock, patch

def _mock_redis():
    r = MagicMock()
    r.get.return_value = None  # no cache
    return r

def test_convert_usd_to_inr():
    with patch("app.services.fx.redis_client", _mock_redis()):
        from app.services.fx import convert
        result = convert(100, "USD", "INR")
        assert result["converted"] > 0
        assert result["from"] == "USD"
        assert result["to"] == "INR"

def test_convert_same_currency():
    with patch("app.services.fx.redis_client", _mock_redis()):
        from app.services.fx import convert
        result = convert(100, "USD", "USD")
        assert result["converted"] == pytest.approx(100.0, rel=1e-3)

def test_unknown_currency_raises():
    with patch("app.services.fx.redis_client", _mock_redis()):
        from app.services.fx import convert
        with pytest.raises(ValueError):
            convert(100, "XYZ", "USD")

def test_normalize_to_base():
    with patch("app.services.fx.redis_client", _mock_redis()):
        from app.services.fx import normalize_to_base
        items = [{"amount": 100, "currency": "USD"}, {"amount": 8350, "currency": "INR"}]
        result = normalize_to_base(items, "USD")
        assert result["base"] == "USD"
        assert result["total"] > 100
