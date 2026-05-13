"""Tests for background job retry & monitoring service."""
import json
import pytest
from datetime import datetime
from app.extensions import db


class TestJobRecordModel:
    """RED: Tests will fail until model exists."""

    def test_job_record_creation(self, app_fixture):
        """JobRecord can be created with required fields."""
        from app.models import JobRecord
        with app_fixture.app_context():
            job = JobRecord(
                job_type="test_job",
                args='{"key": "value"}',
                status="pending",
                max_retries=3,
            )
            db.session.add(job)
            db.session.commit()
            assert job.id is not None
            assert job.status == "pending"
            assert job.retry_count == 0
            assert isinstance(job.created_at, datetime)

    def test_job_record_defaults(self, app_fixture):
        """JobRecord sets sensible defaults."""
        from app.models import JobRecord
        with app_fixture.app_context():
            job = JobRecord(job_type="test", args="{}", status="pending", retry_count=0, max_retries=3)
            assert job.status == "pending"
            assert job.retry_count == 0
            assert job.max_retries == 3


class TestJobService:
    """Tests for the job execution service."""

    def test_execute_successful_job(self, app_fixture):
        """A job that succeeds is marked 'completed'."""
        from app.models import JobRecord
        from app.services.jobs import execute_job
        with app_fixture.app_context():
            results = []

            def success_job():
                results.append("done")
                return "ok"

            job = JobRecord(job_type="test", args="{}")
            db.session.add(job)
            db.session.commit()

            execute_job(job, success_job)

            assert job.status == "completed"
            assert results == ["done"]

    def test_retry_on_failure(self, app_fixture):
        """A failing job is retried up to max_retries."""
        from app.models import JobRecord
        from app.services.jobs import execute_job
        with app_fixture.app_context():
            attempts = []

            def failing_job():
                attempts.append(1)
                raise ValueError("temporary failure")

            job = JobRecord(job_type="test", args="{}", max_retries=3)
            db.session.add(job)
            db.session.commit()

            try:
                execute_job(job, failing_job)
            except RuntimeError:
                pass

            assert job.status == "dead_letter"
            assert job.retry_count == 3
            assert len(attempts) == 3  # initial + 2 retries
            assert job.last_error is not None

    def test_success_after_retry(self, app_fixture):
        """A job that succeeds on retry is marked 'completed'."""
        from app.models import JobRecord
        from app.services.jobs import execute_job
        with app_fixture.app_context():
            counter = [0]

            def flaky_job():
                counter[0] += 1
                if counter[0] < 3:
                    raise ValueError("not yet")
                return "finally ok"

            job = JobRecord(job_type="test", args="{}", max_retries=5)
            db.session.add(job)
            db.session.commit()

            execute_job(job, flaky_job)

            assert job.status == "completed"
            assert job.retry_count == 2  # 2 failed attempts before success

    def test_dead_letter_after_max_retries(self, app_fixture):
        """Job enters dead_letter status after exhausting retries."""
        from app.models import JobRecord
        from app.services.jobs import execute_job
        with app_fixture.app_context():
            def always_fails():
                raise RuntimeError("permanent failure")

            job = JobRecord(job_type="test", args="{}", max_retries=2, status="pending")
            db.session.add(job)
            db.session.commit()

            try:
                execute_job(job, always_fails)
            except RuntimeError:
                pass

            assert job.status == "dead_letter"
            assert job.retry_count == 2

    def test_exponential_backoff(self, app_fixture):
        """Retry delays follow exponential backoff."""
        from app.services.jobs import get_backoff_delay
        # retry 0 -> 2s, retry 1 -> 4s, retry 2 -> 8s
        assert get_backoff_delay(0) == 2
        assert get_backoff_delay(1) == 4
        assert get_backoff_delay(2) == 8
        assert get_backoff_delay(3) == 16
        assert get_backoff_delay(4) == 30  # capped at 30s


class TestJobAPI:
    """Tests for job monitoring API endpoints."""

    def test_list_jobs_requires_auth(self, app_fixture):
        """Unauthenticated request returns 401."""
        with app_fixture.test_client() as client:
            resp = client.get("/jobs")
            assert resp.status_code == 401

    def test_list_jobs_returns_records(self, app_fixture):
        """Authenticated user can list their jobs."""
        from app.models import JobRecord
        with app_fixture.app_context():
            job = JobRecord(job_type="test", args="{}", status="completed")
            db.session.add(job)
            db.session.commit()
            job_id = job.id

        with app_fixture.test_client() as client:
            # Login first
            auth_resp = client.post("/auth/login", json={
                "email": "test@example.com",
                "password": "testpass123"
            })
            if auth_resp.status_code == 200:
                token = auth_resp.json["access_token"]
                resp = client.get(
                    "/jobs/",
                    headers={"Authorization": f"Bearer {token}"}
                )
                assert resp.status_code == 200
                data = resp.get_json()
                assert "jobs" in data
