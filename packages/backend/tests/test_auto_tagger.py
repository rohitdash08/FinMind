"""Tests for auto-tagging (issue #107)."""
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_redis():
    store = {}
    r = MagicMock()
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    def setex(k,t,v): store[k]=v
    r.get.side_effect=get; r.setex.side_effect=setex
    return r, store

def test_suggest_transport(mock_redis):
    r,_ = mock_redis
    with patch("app.services.auto_tagger.redis_client", r):
        from app.services.auto_tagger import suggest_category
        result = suggest_category(1, "UBER TRIP NYC")
        assert result["category"] == "Transport"

def test_suggest_dining(mock_redis):
    r,_ = mock_redis
    with patch("app.services.auto_tagger.redis_client", r):
        from app.services.auto_tagger import suggest_category
        result = suggest_category(1, "Starbucks Coffee")
        assert result["category"] == "Dining"

def test_suggest_none_for_unknown(mock_redis):
    r,_ = mock_redis
    with patch("app.services.auto_tagger.redis_client", r):
        from app.services.auto_tagger import suggest_category
        result = suggest_category(1, "XKQZPP RANDOM CHARGE")
        assert result is None

def test_custom_rule_takes_priority(mock_redis):
    r,_ = mock_redis
    with patch("app.services.auto_tagger.redis_client", r):
        from app.services.auto_tagger import add_rule, suggest_category
        add_rule(1, r"xkqzpp", "Mystery")
        result = suggest_category(1, "XKQZPP RANDOM CHARGE")
        assert result["category"] == "Mystery"
        assert result["confidence"] == "high"
