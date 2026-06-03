"""
Tests for smart caching with Redis backend and local fallback.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app.services.cache_manager import CacheManager, cache
from app.extensions import db


class TestCacheManagerInit:
    """Test CacheManager initialization."""

    def test_default_values(self):
        cm = CacheManager()
        assert cm.default_ttl == 300
        assert cm.max_local_items == 1000
        assert cm.redis is None

    def test_custom_values(self):
        redis_mock = MagicMock()
        cm = CacheManager(redis_client=redis_mock, default_ttl=600, max_local_items=500)
        assert cm.default_ttl == 600
        assert cm.max_local_items == 500
        assert cm.redis is redis_mock


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_basic_key(self):
        cm = CacheManager()
        key = cm._key("user", 123)
        assert key == "user:123"

    def test_key_with_params(self):
        cm = CacheManager()
        key = cm._key("user", 123, {"page": 1, "limit": 10})
        assert key.startswith("user:123:")
        assert len(key) == len("user:123:") + 8  # 8 char hash

    def test_key_consistency(self):
        cm = CacheManager()
        key1 = cm._key("user", 123, {"a": 1, "b": 2})
        key2 = cm._key("user", 123, {"b": 2, "a": 1})  # Different order
        assert key1 == key2  # Should be same due to sort_keys


class TestLocalCache:
    """Test local cache operations."""

    def test_set_and_get(self):
        cm = CacheManager()
        cm.set("key1", {"data": "value1"})
        result = cm.get("key1")
        assert result == {"data": "value1"}

    def test_get_expired(self):
        cm = CacheManager()
        # Set with 0 TTL
        cm.set("key1", "value1", ttl=0)
        # Manually expire
        cm._local["key1"]["exp"] = datetime.utcnow() - timedelta(seconds=1)
        result = cm.get("key1")
        assert result is None

    def test_get_nonexistent(self):
        cm = CacheManager()
        result = cm.get("nonexistent")
        assert result is None

    def test_invalidate_by_tag(self):
        cm = CacheManager()
        cm.set("key1", "value1", tags=["tag1", "tag2"])
        cm.set("key2", "value2", tags=["tag1"])
        cm.set("key3", "value3", tags=["tag2"])
        
        cm.invalidate_by_tag("tag1")
        
        assert cm.get("key1") is None
        assert cm.get("key2") is None
        assert cm.get("key3") == "value3"

    def test_invalidate_user(self):
        cm = CacheManager()
        cm.set("key1", "value1", tags=["user:123"])
        cm.set("key2", "value2", tags=["user:456"])
        
        cm.invalidate_user(123)
        
        assert cm.get("key1") is None
        assert cm.get("key2") == "value2"

    def test_eviction(self):
        cm = CacheManager(max_local_items=5)
        
        # Add 6 items
        for i in range(6):
            cm.set(f"key{i}", f"value{i}")
        
        # Should have evicted some items
        assert len(cm._local) <= 5


class TestRedisCache:
    """Test Redis cache operations."""

    def test_set_with_redis(self):
        redis_mock = MagicMock()
        cm = CacheManager(redis_client=redis_mock)
        
        cm.set("key1", {"data": "value1"}, ttl=60, tags=["tag1"])
        
        redis_mock.setex.assert_called_once()
        redis_mock.sadd.assert_called_once()
        redis_mock.expire.assert_called_once()

    def test_get_from_redis(self):
        redis_mock = MagicMock()
        redis_mock.get.return_value = '{"data": "value1"}'
        cm = CacheManager(redis_client=redis_mock)
        
        result = cm.get("key1")
        assert result == {"data": "value1"}

    def test_redis_failure_fallback(self):
        redis_mock = MagicMock()
        redis_mock.get.side_effect = Exception("Redis down")
        cm = CacheManager(redis_client=redis_mock)
        
        # Set in local cache
        cm._local["key1"] = {
            "val": "local_value",
            "exp": datetime.utcnow() + timedelta(seconds=300),
            "tags": []
        }
        
        result = cm.get("key1")
        assert result == "local_value"  # Should fallback to local

    def test_redis_set_failure_continues_to_local(self):
        redis_mock = MagicMock()
        redis_mock.setex.side_effect = Exception("Redis down")
        cm = CacheManager(redis_client=redis_mock)
        
        cm.set("key1", "value1")
        
        # Should still be in local cache
        assert cm._local.get("key1") is not None


class TestCachedDecorator:
    """Test cached decorator."""

    def test_cache_hit(self):
        cm = CacheManager()
        call_count = 0
        
        @cm.cached("test")
        def expensive_function(user_id):
            nonlocal call_count
            call_count += 1
            return {"result": "data"}
        
        # First call
        result1 = expensive_function(user_id=123)
        assert call_count == 1
        
        # Second call (should be cached)
        result2 = expensive_function(user_id=123)
        assert call_count == 1
        assert result1 == result2

    def test_cache_miss_different_users(self):
        cm = CacheManager()
        call_count = 0
        
        @cm.cached("test")
        def expensive_function(user_id):
            nonlocal call_count
            call_count += 1
            return {"user": user_id}
        
        expensive_function(user_id=123)
        expensive_function(user_id=456)
        
        assert call_count == 2

    def test_cache_with_tags(self):
        cm = CacheManager()
        
        @cm.cached("test", tags=["user:{user_id}"])
        def get_user_data(user_id):
            return {"data": "value"}
        
        get_user_data(user_id=123)
        
        # Should have cached with user tag
        key = cm._key("test", 123)
        assert cm.get(key) is not None
        
        # Invalidate user cache
        cm.invalidate_user(123)
        assert cm.get(key) is None

    def test_custom_key_func(self):
        cm = CacheManager()
        
        def custom_key(*args, **kwargs):
            return kwargs.get("custom_id", 0)
        
        @cm.cached("test", key_func=custom_key)
        def get_data(custom_id):
            return {"data": custom_id}
        
        get_data(custom_id=123)
        
        # Check cache with custom key
        key = cm._key("test", 123)
        assert cm.get(key) is not None


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
