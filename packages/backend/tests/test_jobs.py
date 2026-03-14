"""Tests for the background job retry and monitoring system."""

import json


def test_create_job(client, auth_header):
    r = client.post(
        "/jobs",
        json={
            "name": "Sync bank data",
            "job_type": "DATA_SYNC",
            "payload": {"source": "plaid"},
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["name"] == "Sync bank data"
    assert data["job_type"] == "DATA_SYNC"
    assert data["status"] == "PENDING"
    assert data["attempts"] == 0
    assert data["max_retries"] == 5
    assert data["id"] is not None


def test_create_job_missing_fields(client, auth_header):
    r = client.post("/jobs", json={"name": "test"}, headers=auth_header)
    assert r.status_code == 400
    assert "required" in r.get_json()["error"].lower()


def test_create_job_invalid_type(client, auth_header):
    r = client.post(
        "/jobs",
        json={"name": "test", "job_type": "INVALID_TYPE"},
        headers=auth_header,
    )
    assert r.status_code == 400
    assert "Invalid job_type" in r.get_json()["error"]


def test_list_jobs(client, auth_header):
    # Create a few jobs
    for name in ["Job A", "Job B"]:
        client.post(
            "/jobs",
            json={"name": name, "job_type": "DATA_SYNC"},
            headers=auth_header,
        )

    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] >= 2
    assert len(data["jobs"]) >= 2


def test_list_jobs_filter_by_status(client, auth_header):
    client.post(
        "/jobs",
        json={"name": "Filter test", "job_type": "DATA_SYNC"},
        headers=auth_header,
    )

    r = client.get("/jobs?status=PENDING", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    for job in data["jobs"]:
        assert job["status"] == "PENDING"


def test_list_jobs_filter_by_job_type(client, auth_header):
    client.post(
        "/jobs",
        json={"name": "Report job", "job_type": "REPORT_GENERATION"},
        headers=auth_header,
    )

    r = client.get("/jobs?job_type=REPORT_GENERATION", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    for job in data["jobs"]:
        assert job["job_type"] == "REPORT_GENERATION"


def test_get_job(client, auth_header):
    r = client.post(
        "/jobs",
        json={"name": "Get test", "job_type": "EMAIL_NOTIFICATION"},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json()["id"] == job_id


def test_get_job_not_found(client, auth_header):
    r = client.get("/jobs/99999", headers=auth_header)
    assert r.status_code == 404


def test_retry_failed_job(client, auth_header):
    # Create and then manually fail a job via direct model manipulation
    from app.extensions import db
    from app.models import BackgroundJob, JobStatus

    r = client.post(
        "/jobs",
        json={
            "name": "Will fail",
            "job_type": "DATA_SYNC",
            "payload": {"source": "test"},
        },
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    # Manually mark as failed
    with client.application.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.FAILED.value
        job.attempts = 2
        job.last_error = "Simulated failure"
        db.session.commit()

    # Retry it
    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    # After retry+execute, it should be COMPLETED (handler succeeds)
    assert data["status"] == "COMPLETED"
    assert data["attempts"] == 3  # incremented by execute


def test_retry_completed_job_fails(client, auth_header):
    from app.extensions import db
    from app.models import BackgroundJob, JobStatus

    r = client.post(
        "/jobs",
        json={"name": "Completed job", "job_type": "DATA_SYNC"},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    with client.application.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.COMPLETED.value
        db.session.commit()

    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 400
    assert "Cannot retry" in r.get_json()["error"]


def test_retry_dead_job(client, auth_header):
    from app.extensions import db
    from app.models import BackgroundJob, JobStatus

    r = client.post(
        "/jobs",
        json={"name": "Dead job", "job_type": "REPORT_GENERATION"},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    with client.application.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.DEAD.value
        job.attempts = 5
        job.last_error = "Max retries exceeded"
        db.session.commit()

    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "COMPLETED"


def test_job_stats(client, auth_header):
    # Create a couple of jobs
    client.post(
        "/jobs",
        json={"name": "Stats A", "job_type": "DATA_SYNC"},
        headers=auth_header,
    )
    client.post(
        "/jobs",
        json={"name": "Stats B", "job_type": "EMAIL_NOTIFICATION"},
        headers=auth_header,
    )

    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "pending" in data
    assert "running" in data
    assert "completed" in data
    assert "failed" in data
    assert "dead" in data
    assert "total" in data
    assert data["total"] >= 2


def test_dead_letter_queue(client, auth_header):
    from app.extensions import db
    from app.models import BackgroundJob, JobStatus

    r = client.post(
        "/jobs",
        json={"name": "DLQ test", "job_type": "DATA_SYNC"},
        headers=auth_header,
    )
    job_id = r.get_json()["id"]

    with client.application.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.DEAD.value
        job.last_error = "Permanent failure"
        db.session.commit()

    r = client.get("/jobs/dead-letter", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    dead_ids = [j["id"] for j in data]
    assert job_id in dead_ids


def test_exponential_backoff():
    """Test that the backoff calculation produces increasing delays."""
    from app.services.job_queue import _compute_next_retry
    from datetime import datetime

    delays = []
    for attempt in range(1, 6):
        before = datetime.utcnow()
        next_retry = _compute_next_retry(attempt)
        delay = (next_retry - before).total_seconds()
        delays.append(delay)

    # Each delay should be roughly >= 2^attempt (minus jitter noise)
    for i, delay in enumerate(delays):
        expected_min = 2 ** (i + 1)
        # Allow some tolerance for jitter
        assert delay >= expected_min - 0.5, (
            f"Attempt {i + 1}: delay {delay}s < expected min {expected_min}s"
        )

    # Delays should be strictly increasing on average
    assert delays[-1] > delays[0]


def test_execute_job_moves_to_dead_after_max_retries(client, auth_header):
    """Job should move to DEAD status when attempts >= max_retries."""
    from app.extensions import db
    from app.models import BackgroundJob, JobStatus
    from app.services.job_queue import execute_job, register_handler

    # Register a handler that always fails
    def _always_fail(payload):
        raise RuntimeError("Always fails")

    register_handler("DATA_SYNC", _always_fail)

    try:
        r = client.post(
            "/jobs",
            json={
                "name": "Max retry test",
                "job_type": "DATA_SYNC",
                "max_retries": 1,
            },
            headers=auth_header,
        )
        job_id = r.get_json()["id"]

        with client.application.app_context():
            job = db.session.get(BackgroundJob, job_id)
            execute_job(job)
            # After 1 attempt with max_retries=1, should be DEAD
            assert job.status == JobStatus.DEAD.value
            assert job.attempts == 1
            assert "Always fails" in job.last_error
    finally:
        # Restore the real handler
        from app.services.job_queue import _handle_data_sync

        register_handler("DATA_SYNC", _handle_data_sync)


def test_create_job_with_scheduled_at(client, auth_header):
    r = client.post(
        "/jobs",
        json={
            "name": "Future job",
            "job_type": "REPORT_GENERATION",
            "scheduled_at": "2099-01-01T00:00:00",
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["scheduled_at"] is not None
    assert "2099" in data["scheduled_at"]


def test_create_job_custom_max_retries(client, auth_header):
    r = client.post(
        "/jobs",
        json={
            "name": "Custom retries",
            "job_type": "EMAIL_NOTIFICATION",
            "max_retries": 10,
        },
        headers=auth_header,
    )
    assert r.status_code == 201
    assert r.get_json()["max_retries"] == 10


def test_pagination(client, auth_header):
    for i in range(5):
        client.post(
            "/jobs",
            json={"name": f"Page test {i}", "job_type": "DATA_SYNC"},
            headers=auth_header,
        )

    r = client.get("/jobs?page=1&per_page=2", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["jobs"]) == 2
    assert data["per_page"] == 2
    assert data["page"] == 1
    assert data["total"] >= 5


def test_unauthenticated_access(client):
    r = client.get("/jobs")
    assert r.status_code == 401

    r = client.post("/jobs", json={"name": "test", "job_type": "DATA_SYNC"})
    assert r.status_code == 401
