"""
Tests for background job retry with exponential backoff.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.services.retry import (
    RetryConfig,
    retry_with_backoff,
)
from app.extensions import db


class TestRetryConfig:
    """Test RetryConfig configuration."""

    def test_default_config(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.backoff_factor == 2.0

    def test_custom_config(self):
        config = RetryConfig(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            backoff_factor=3.0
        )
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert config.backoff_factor == 3.0


class TestRetryWithBackoff:
    """Test retry_with_backoff decorator."""

    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        call_count = 0
        
        @retry_with_backoff()
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_function()
        assert result == "success"
        assert call_count == 1

    def test_success_after_retries(self):
        """Test function succeeds after some failures."""
        call_count = 0
        
        @retry_with_backoff(RetryConfig(max_retries=3, base_delay=0.01))
        def eventually_successful():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Attempt {call_count} failed")
            return "success"
        
        result = eventually_successful()
        assert result == "success"
        assert call_count == 3

    def test_failure_after_max_retries(self):
        """Test function fails after max retries exceeded."""
        call_count = 0
        
        @retry_with_backoff(RetryConfig(max_retries=2, base_delay=0.01))
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError(f"Attempt {call_count} failed")
        
        with pytest.raises(ValueError, match="Attempt 3 failed"):
            always_fails()
        
        # max_retries=2 means 3 total attempts (1 initial + 2 retries)
        assert call_count == 3

    def test_exponential_backoff_timing(self):
        """Test that delays increase exponentially."""
        import time
        
        config = RetryConfig(
            max_retries=3,
            base_delay=0.1,
            backoff_factor=2.0,
            max_delay=10.0
        )
        
        call_count = 0
        start_time = time.time()
        
        @retry_with_backoff(config)
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            failing_function()
        
        elapsed = time.time() - start_time
        
        # Should have delays: 0.1, 0.2, 0.4 (total ~0.7s plus execution time)
        assert elapsed >= 0.5  # At least some delay
        assert call_count == 4  # 1 initial + 3 retries

    def test_max_delay_cap(self):
        """Test that delay doesn't exceed max_delay."""
        config = RetryConfig(
            max_retries=5,
            base_delay=1.0,
            backoff_factor=10.0,
            max_delay=2.0  # Cap at 2 seconds
        )
        
        call_count = 0
        import time
        start_time = time.time()
        
        @retry_with_backoff(config)
        def failing_function():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            failing_function()
        
        elapsed = time.time() - start_time
        
        # With max_delay=2.0, total delay should be capped
        # Delays would be: 1.0, 2.0, 2.0, 2.0, 2.0 = 9.0s max
        assert elapsed < 15.0  # Should be much less due to cap
        assert call_count == 6  # 1 initial + 5 retries


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
