"""
Tests for background job retry with exponential backoff.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from app.services.job_retry import (
    JobRetry,
    RetryPolicy,
    JobStatus,
    submit_job,
    retry_job,
    get_job_status,
)
from app.extensions import db


class TestRetryPolicy:
    """Test RetryPolicy configuration."""

    def test_default_policy(self):
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 60.0
        assert policy.exponential_base == 2.0

    def test_custom_policy(self):
        policy = RetryPolicy(
            max_retries=5,
            base_delay=2.0,
            max_delay=120.0,
            exponential_base=3.0,
        )
        assert policy.max_retries == 5
        assert policy.base_delay == 2.0
        assert policy.max_delay == 120.0
        assert policy.exponential_base == 3.0

    def test_calculate_delay(self):
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        
        # Attempt 0: 1.0 * 2^0 = 1.0
        assert policy.calculate_delay(0) == 1.0
        
        # Attempt 1: 1.0 * 2^1 = 2.0
        assert policy.calculate_delay(1) == 2.0
        
        # Attempt 2: 1.0 * 2^2 = 4.0
        assert policy.calculate_delay(2) == 4.0

    def test_max_delay_cap(self):
        policy = RetryPolicy(base_delay=1.0, max_delay=5.0, exponential_base=2.0)
        
        # Attempt 10: 1.0 * 2^10 = 1024.0, but capped at 5.0
        assert policy.calculate_delay(10) == 5.0


class TestJobRetry:
    """Test JobRetry class."""

    def test_submit_job(self, app, db):
        with app.app_context():
            retry = JobRetry()
            
            job_id = retry.submit(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                kwargs={},
            )
            
            assert job_id is not None
            
            job = retry.get_job(job_id)
            assert job.status == JobStatus.PENDING
            assert job.attempts == 0

    def test_retry_job_success(self, app, db):
        with app.app_context():
            retry = JobRetry()
            
            # Submit job
            job_id = retry.submit(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                kwargs={},
            )
            
            # Mock successful execution
            with patch("app.tasks.send_email") as mock_func:
                mock_func.return_value = True
                
                # Execute job
                result = retry.execute(job_id)
                
                assert result.success is True
                assert result.attempts == 1

    def test_retry_job_failure_and_retry(self, app, db):
        with app.app_context():
            retry = JobRetry()
            
            # Submit job
            job_id = retry.submit(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                kwargs={},
            )
            
            # Mock failed execution
            with patch("app.tasks.send_email") as mock_func:
                mock_func.side_effect = Exception("Network error")
                
                # Execute job (should fail and schedule retry)
                result = retry.execute(job_id)
                
                assert result.success is False
                assert result.attempts == 1
                assert result.next_retry_at is not None

    def test_retry_exhaustion(self, app, db):
        with app.app_context():
            retry = JobRetry(policy=RetryPolicy(max_retries=2))
            
            # Submit job
            job_id = retry.submit(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                kwargs={},
            )
            
            # Mock failed execution
            with patch("app.tasks.send_email") as mock_func:
                mock_func.side_effect = Exception("Network error")
                
                # Execute job multiple times
                for i in range(3):
                    result = retry.execute(job_id)
                
                # Should be exhausted
                job = retry.get_job(job_id)
                assert job.status == JobStatus.FAILED
                assert job.attempts == 3

    def test_cancel_job(self, app, db):
        with app.app_context():
            retry = JobRetry()
            
            # Submit job
            job_id = retry.submit(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                kwargs={},
            )
            
            # Cancel job
            retry.cancel(job_id)
            
            job = retry.get_job(job_id)
            assert job.status == JobStatus.CANCELLED


class TestSubmitJob:
    """Test submit_job helper function."""

    def test_submit_job_function(self, app, db):
        with app.app_context():
            job_id = submit_job(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
            )
            
            assert job_id is not None

    def test_submit_with_retry_policy(self, app, db):
        with app.app_context():
            policy = RetryPolicy(max_retries=5)
            
            job_id = submit_job(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
                retry_policy=policy,
            )
            
            assert job_id is not None


class TestRetryJob:
    """Test retry_job helper function."""

    def test_retry_failed_job(self, app, db):
        with app.app_context():
            # Submit and fail a job
            job_id = submit_job(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
            )
            
            # Mock failure
            with patch("app.tasks.send_email") as mock_func:
                mock_func.side_effect = Exception("Failed")
                
                # Execute to fail
                retry = JobRetry()
                retry.execute(job_id)
                
                # Retry the job
                result = retry_job(job_id)
                
                assert result.success is None  # Pending retry
                assert result.attempts == 0  # Reset

    def test_retry_nonexistent_job(self, app, db):
        with app.app_context():
            with pytest.raises(ValueError):
                retry_job("nonexistent_job_id")


class TestGetJobStatus:
    """Test get_job_status helper function."""

    def test_get_status_pending(self, app, db):
        with app.app_context():
            job_id = submit_job(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
            )
            
            status = get_job_status(job_id)
            assert status == JobStatus.PENDING

    def test_get_status_completed(self, app, db):
        with app.app_context():
            job_id = submit_job(
                func="app.tasks.send_email",
                args=["user@example.com", "Test"],
            )
            
            # Execute successfully
            with patch("app.tasks.send_email") as mock_func:
                mock_func.return_value = True
                
                retry = JobRetry()
                retry.execute(job_id)
                
                status = get_job_status(job_id)
                assert status == JobStatus.COMPLETED

    def test_get_status_nonexistent(self, app, db):
        with app.app_context():
            with pytest.raises(ValueError):
                get_job_status("nonexistent_job_id")


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
