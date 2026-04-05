"""Tests for payee alias management (issue #114)."""
import pytest
from unittest.mock import MagicMock, patch
import json

@pytest.fixture
def mock_redis():
    store = {}
    r = MagicMock()
    def setex(k,t,v): store[k]=v
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    r.setex.side_effect=setex; r.get.side_effect=get
    return r, store

def test_set_and_get_alias(mock_redis):
    r,_ = mock_redis
    with patch("app.services.payee_alias.redis_client", r):
        from app.services.payee_alias import set_alias, get_alias
        set_alias(1, "AMZN MKTP US*AB1234", "Amazon")
        result = get_alias(1, "AMZN MKTP US*AB1234")
        assert result["alias"] == "Amazon"

def test_resolve_with_alias(mock_redis):
    r,_ = mock_redis
    with patch("app.services.payee_alias.redis_client", r):
        from app.services.payee_alias import set_alias, resolve
        set_alias(1, "STARBUCKS #4521", "Starbucks")
        assert resolve(1, "STARBUCKS #4521") == "Starbucks"

def test_resolve_auto_clean(mock_redis):
    r,_ = mock_redis
    with patch("app.services.payee_alias.redis_client", r):
        from app.services.payee_alias import resolve
        cleaned = resolve(1, "WALMART STORE 4521  ")
        assert "4521" not in cleaned  # numeric code stripped
        assert cleaned == cleaned.strip()

def test_delete_alias(mock_redis):
    r,_ = mock_redis
    with patch("app.services.payee_alias.redis_client", r):
        from app.services.payee_alias import set_alias, delete_alias, get_alias
        set_alias(1, "Netflix", "Netflix Sub")
        assert delete_alias(1, "Netflix") is True
        assert get_alias(1, "Netflix") is None
