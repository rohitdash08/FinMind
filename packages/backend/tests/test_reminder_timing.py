"""Tests for smart reminder timing (issue #111)."""
import json, pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def mock_redis():
    store = {}
    r = MagicMock()
    def setex(k,t,v): store[k]=v
    def get(k): v=store.get(k); return v.encode() if isinstance(v,str) else v
    r.setex.side_effect=setex; r.get.side_effect=get
    return r, store

def test_default_when_no_data(mock_redis):
    r,_ = mock_redis
    with patch("app.services.reminder_timing.redis_client", r):
        from app.services.reminder_timing import get_optimal_time
        result = get_optimal_time(1)
        assert result["hour"] == 9
        assert result["confidence"] == "low"

def test_record_and_optimize(mock_redis):
    r,_ = mock_redis
    with patch("app.services.reminder_timing.redis_client", r):
        from app.services.reminder_timing import record_engagement, get_optimal_time
        for _ in range(10): record_engagement(1, 9, 0)   # Monday 9AM x10
        for _ in range(2): record_engagement(1, 14, 2)   # Wednesday 2PM x2
        result = get_optimal_time(1)
        assert result["hour"] == 9
        assert result["day_of_week"] == 0

def test_high_confidence_threshold(mock_redis):
    r,_ = mock_redis
    with patch("app.services.reminder_timing.redis_client", r):
        from app.services.reminder_timing import record_engagement, get_optimal_time
        for _ in range(8): record_engagement(2, 18, 4)
        for _ in range(2): record_engagement(2, 10, 1)
        result = get_optimal_time(2)
        assert result["confidence"] == "high"
