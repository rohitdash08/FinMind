"""
Tests for the background job service with retry and monitoring.

Tests cover:
- Job creation and enqueueing
- Retry logic with exponential backoff
- Dead letter queue handling
- Job metrics
- API endpoints
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
import time

from app.services.background_jobs import (
    BackgroundJobService,
    BackgroundJob,
    JobStatus,
    JobType,
    RetryConfig,
    job_metrics,
)
from app.extensions import db


@pytest.fixture(autouse=True)
def reset_metrics():
    """Reset metrics before each test."""
    job_metrics._jobs_created = 0
    job_metrics._jobs_succeeded = 0
    job_metrics._jobs_failed = 0
    job_metrics._jobs_retried = 0
    job_metrics._jobs_dead_letter = 0
    job_metrics._total_processing_time_ms = 0


class TestBackgroundJobModel:
    """Tests for the BackgroundJob model."""

    def test_create_job(self, app, db_session):
        """Test creating a background job."""
        with app.app_context():
            job = BackgroundJob(
                job_type=JobType.SEND_EMAIL.value,
                payload={"to": "test@example.com", "subject": "Test"},
                status=JobStatus.PENDING.value,
            )
            db.session.add(job)
            db.session.commit()

            assert job.id is not None
            assert job.job_type == JobType.SEND_EMAIL.value
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 0
            assert job.created_at is not None

    def test_job_status_transitions(self, app, db_session):
        """Test job status transitions."""
        with app.app_context():
            job = BackgroundJob(
                job_type=JobType.SEND_REMINDER.value,
                status=JobStatus.PENDING.value,
            )
            db.session.add(job)
            db.session.commit()

            # Transition to running
            job.status = JobStatus.RUNNING.value
            job.started_at = datetime.utcnow()
            db.session.commit()

            assert job.status == JobStatus.RUNNING.value
            assert job.started_at is not None


class TestRetryLogic:
    """Tests for retry and backoff logic."""

    def test_calculate_backoff_delay(self):
        """Test exponential backoff calculation."""
        config = RetryConfig(
            max_retries=3,
            initial_delay_seconds=1.0,
            max_delay_seconds=300.0,
            backoff_multiplier=2.0,
            jitter=False,
        )

        # First retry: 1 * 2^0 = 1 second
        delay_0 = BackgroundJobService.calculate_backoff_delay(0, config)
        assert delay_0 == 1.0

        # Second retry: 1 * 2^1 = 2 seconds
        delay_1 = BackgroundJobService.calculate_backoff_delay(1, config)
        assert delay_1 == 2.0

        # Third retry: 1 * 2^2 = 4 seconds
        delay_2 = BackgroundJobService.calculate_backoff_delay(2, config)
        assert delay_2 == 4.0

    def test_backoff_with_max_delay(self):
        """Test that backoff doesn't exceed max delay."""
        config = RetryConfig(
            max_delay_seconds=10.0,
            initial_delay_seconds=1.0,
            backoff_multiplier=2.0,
            jitter=False,
        )

        # With high retry count, should cap at max_delay
        delay = BackgroundJobService.calculate_backoff_delay(10, config)
        assert delay == 10.0

    def test_backoff_with_jitter(self):
        """Test that jitter is applied to backoff."""
        config = RetryConfig(
            initial_delay_seconds=10.0,
            jitter=True,
        )

        # Calculate multiple delays - they should vary due to jitter
        delays = [
            BackgroundJobService.calculate_backoff_delay(1, config)
            for _ in range(10)
        ]

        # All delays should be within ±25% of base
        base_delay = 20.0  # 10.0 * 2^1
        for d in delays:
            assert 0.75 * base_delay <= d <= 1.25 * base_delay

    def test_successful_job_no_retry(self, app, db_session):
        """Test that successful jobs don't retry."""
        with app.app_context():
            # Register a successful handler
            def success_handler(payload):
                return {"result": "ok"}

            BackgroundJobService.register_handler(JobType.SEND_EMAIL, success_handler)

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"test": True},
            )

            # Execute the job
            result = BackgroundJobService.execute_job(job)
            assert result is True

            # Verify job status
            assert job.status == JobStatus.SUCCEEDED.value
            assert job.retry_count == 0

    def test_failed_job_retries(self, app, db_session):
        """Test that failed jobs retry up to max_retries."""
        with app.app_context():
            # Register a failing handler
            fail_count = [0]

            def failing_handler(payload):
                fail_count[0] += 1
                raise Exception(f"Intentional failure {fail_count[0]}")

            BackgroundJobService.register_handler(JobType.SEND_EMAIL, failing_handler)

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"test": True},
                max_retries=2,
            )

            # Execute job - should fail and retry
            result_1 = BackgroundJobService.execute_job(job)
            assert result_1 is False
            assert job.status == JobStatus.RETRYING.value
            assert job.retry_count == 1

            # Execute again - should fail and retry again
            result_2 = BackgroundJobService.execute_job(job)
            assert result_2 is False
            assert job.retry_count == 2

            # Execute again - should hit max retries and go to dead letter
            result_3 = BackgroundJobService.execute_job(job)
            assert result_3 is False
            assert job.status == JobStatus.DEAD_LETTER.value

    def test_dead_letter_queue(self, app, db_session):
        """Test that permanently failed jobs go to dead letter queue."""
        with app.app_context():
            # Register a failing handler
            def failing_handler(payload):
                raise Exception("Permanent failure")

            BackgroundJobService.register_handler(JobType.SEND_REMINDER, failing_handler)

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_REMINDER,
                max_retries=1,
            )

            # Execute twice to exceed max retries
            BackgroundJobService.execute_job(job)
            BackgroundJobService.execute_job(job)

            assert job.status == JobStatus.DEAD_LETTER.value
            assert job.last_error is not None

            # Verify it's in dead letter queue
            dead_letter = BackgroundJobService.get_dead_letter_jobs()
            assert len(dead_letter) >= 1
            assert any(j["id"] == job.id for j in dead_letter)


class TestJobMetrics:
    """Tests for job metrics tracking."""

    def test_metrics_created_on_enqueue(self, app, db_session):
        """Test that metrics are updated when job is enqueued."""
        with app.app_context():
            initial_count = job_metrics._jobs_created

            BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"test": True},
            )

            assert job_metrics._jobs_created == initial_count + 1

    def test_metrics_success(self, app, db_session):
        """Test that successful jobs update success metrics."""
        with app.app_context():
            BackgroundJobService.register_handler(
                JobType.SEND_EMAIL,
                lambda p: {"ok": True}
            )

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
            )

            BackgroundJobService.execute_job(job)

            assert job_metrics._jobs_succeeded == 1
            assert job_metrics._total_processing_time_ms > 0

    def test_metrics_retry(self, app, db_session):
        """Test that retries update retry metrics."""
        with app.app_context():
            BackgroundJobService.register_handler(
                JobType.SEND_REMINDER,
                lambda p: (_ for _ in ()).throw(Exception("fail"))
            )

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_REMINDER,
                max_retries=2,
            )

            BackgroundJobService.execute_job(job)

            assert job_metrics._jobs_retried == 1

    def test_metrics_dead_letter(self, app, db_session):
        """Test that dead letter jobs update dead letter metrics."""
        with app.app_context():
            BackgroundJobService.register_handler(
                JobType.SEND_WHATSAPP,
                lambda p: (_ for _ in ()).throw(Exception("fail"))
            )

            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_WHATSAPP,
                max_retries=0,  # No retries
            )

            BackgroundJobService.execute_job(job)

            assert job_metrics._jobs_dead_letter == 1


class TestJobProcessing:
    """Tests for batch job processing."""

    def test_process_pending_jobs(self, app, db_session):
        """Test processing multiple pending jobs."""
        with app.app_context():
            BackgroundJobService.register_handler(
                JobType.SEND_EMAIL,
                lambda p: {"ok": True}
            )

            # Create multiple jobs
            for i in range(3):
                BackgroundJobService.enqueue(
                    job_type=JobType.SEND_EMAIL,
                    payload={"index": i},
                )

            stats = BackgroundJobService.process_pending_jobs(limit=10)

            assert stats["processed"] == 3
            assert stats["succeeded"] == 3
            assert stats["failed"] == 0

    def test_process_jobs_priority_order(self, app, db_session):
        """Test that jobs are processed in priority order."""
        with app.app_context():
            processed_order = []

            def tracking_handler(payload):
                processed_order.append(payload.get("id"))
                return {"ok": True}

            BackgroundJobService.register_handler(JobType.SEND_EMAIL, tracking_handler)

            # Create jobs with different priorities
            BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"id": "low"},
                priority=0,
            )
            BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"id": "high"},
                priority=10,
            )
            BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"id": "medium"},
                priority=5,
            )

            BackgroundJobService.process_pending_jobs(limit=10)

            # Higher priority jobs should be processed first
            assert processed_order == ["high", "medium", "low"]


class TestJobCleanup:
    """Tests for job cleanup functionality."""

    def test_cleanup_old_jobs(self, app, db_session):
        """Test that old completed jobs are cleaned up."""
        with app.app_context():
            # Create an old completed job
            old_job = BackgroundJob(
                job_type=JobType.SEND_EMAIL.value,
                status=JobStatus.SUCCEEDED.value,
                completed_at=datetime.utcnow() - timedelta(days=60),
            )
            db.session.add(old_job)
            db.session.commit()

            # Create a recent completed job
            recent_job = BackgroundJob(
                job_type=JobType.SEND_EMAIL.value,
                status=JobStatus.SUCCEEDED.value,
                completed_at=datetime.utcnow() - timedelta(days=5),
            )
            db.session.add(recent_job)
            db.session.commit()

            # Cleanup jobs older than 30 days
            deleted = BackgroundJobService.cleanup_old_jobs(days=30)

            assert deleted >= 1

            # Verify old job is deleted and recent job remains
            assert BackgroundJob.query.get(old_job.id) is None
            assert BackgroundJob.query.get(recent_job.id) is not None


class TestManualRetry:
    """Tests for manual retry functionality."""

    def test_retry_dead_letter_job(self, app, db_session):
        """Test manually retrying a dead letter job."""
        with app.app_context():
            BackgroundJobService.register_handler(
                JobType.SEND_REMINDER,
                lambda p: {"ok": True}
            )

            # Create a dead letter job
            job = BackgroundJob(
                job_type=JobType.SEND_REMINDER.value,
                status=JobStatus.DEAD_LETTER.value,
                retry_count=3,
            )
            db.session.add(job)
            db.session.commit()

            # Retry the job
            success = BackgroundJobService.retry_dead_letter_job(job.id)
            assert success is True

            # Verify job is reset
            job = BackgroundJob.query.get(job.id)
            assert job.status == JobStatus.PENDING.value
            assert job.retry_count == 0


class TestAPIEndpoints:
    """Tests for background job API endpoints."""

    def test_get_metrics_endpoint(self, client):
        """Test GET /api/jobs/metrics endpoint."""
        response = client.get("/api/jobs/metrics")
        assert response.status_code == 200
        data = response.get_json()
        assert "jobs_created" in data
        assert "jobs_succeeded" in data

    def test_get_job_status_endpoint(self, client, app, db_session):
        """Test GET /api/jobs/<id> endpoint."""
        with app.app_context():
            job = BackgroundJobService.enqueue(
                job_type=JobType.SEND_EMAIL,
                payload={"test": True},
            )

        response = client.get(f"/api/jobs/{job.id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["id"] == job.id
        assert data["job_type"] == JobType.SEND_EMAIL.value

    def test_get_job_not_found(self, client):
        """Test GET /api/jobs/<id> with non-existent job."""
        response = client.get("/api/jobs/99999")
        assert response.status_code == 404

    def test_get_pending_jobs_endpoint(self, client, app, db_session):
        """Test GET /api/jobs/pending endpoint."""
        with app.app_context():
            BackgroundJobService.enqueue(job_type=JobType.SEND_EMAIL)

        response = client.get("/api/jobs/pending")
        assert response.status_code == 200
        data = response.get_json()
        assert "jobs" in data
        assert "total" in data

    def test_get_dead_letter_endpoint(self, client, app, db_session):
        """Test GET /api/jobs/dead-letter endpoint."""
        with app.app_context():
            job = BackgroundJob(
                job_type=JobType.SEND_REMINDER.value,
                status=JobStatus.DEAD_LETTER.value,
            )
            db.session.add(job)
            db.session.commit()

        response = client.get("/api/jobs/dead-letter")
        assert response.status_code == 200
        data = response.get_json()
        assert "jobs" in data

    def test_retry_job_endpoint(self, client, app, db_session):
        """Test POST /api/jobs/<id>/retry endpoint."""
        with app.app_context():
            job = BackgroundJob(
                job_type=JobType.SEND_REMINDER.value,
                status=JobStatus.DEAD_LETTER.value,
            )
            db.session.add(job)
            db.session.commit()

            response = client.post(f"/api/jobs/{job.id}/retry")
            assert response.status_code == 200
            data = response.get_json()
            assert data["success"] is True

    def test_health_endpoint(self, client):
        """Test GET /api/jobs/health endpoint."""
        response = client.get("/api/jobs/health")
        assert response.status_code == 200
        data = response.get_json()
        assert "status" in data
        assert "status_counts" in data


# Pytest fixtures
@pytest.fixture
def app():
    """Create test app."""
    from app import create_app
    from app.config import Settings

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRET_KEY="test-secret-key",
        JWT_SECRET="test-jwt-secret",
    )
    app = create_app(settings)
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()

    yield app


@pytest.fixture
def db_session(app):
    """Create database session."""
    with app.app_context():
        yield db


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()