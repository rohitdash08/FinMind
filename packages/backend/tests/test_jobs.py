"""Tests for background jobs API (bounty #130)."""

from datetime import datetime, timedelta

from app.extensions import db
from app.models import BackgroundJob, JobStatus


def test_jobs_create_and_list(client, auth_header):
    """Test creating and listing jobs."""
    payload = {
        "task_type": "test_task",
        "payload": {"message": "hello"},
        "max_attempts": 2,
    }
    r = client.post("/jobs", json=payload, headers=auth_header)
    assert r.status_code == 201
    job = r.get_json()
    job_id = job["id"]
    assert job["task_type"] == "test_task"
    assert job["status"] == "pending"
    assert job["attempts"] == 0
    assert job["max_attempts"] == 2

    r = client.get("/jobs", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1
    assert items[0]["id"] == job_id


def test_jobs_get_by_id(client, auth_header):
    """Test getting a job by ID."""
    payload = {"task_type": "test_task"}
    r = client.post("/jobs", json=payload, headers=auth_header)
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    job = r.get_json()
    assert job["id"] == job_id
    assert job["task_type"] == "test_task"


def test_jobs_get_not_found(client, auth_header):
    """Test getting non-existent job returns 404."""
    r = client.get("/jobs/99999", headers=auth_header)
    assert r.status_code == 404


def test_jobs_create_validation(client, auth_header):
    """Test job creation validation."""
    r = client.post("/jobs", json={}, headers=auth_header)
    assert r.status_code == 400
    assert "task_type required" in r.get_json()["error"]

    r = client.post("/jobs", json={"task_type": 123}, headers=auth_header)
    assert r.status_code == 400


def test_jobs_create_with_scheduled_for(client, auth_header):
    """Test creating a job with scheduled_for."""
    future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
    payload = {
        "task_type": "scheduled_task",
        "scheduled_for": future,
    }
    r = client.post("/jobs", json=payload, headers=auth_header)
    assert r.status_code == 201
    job = r.get_json()
    assert job["scheduled_for"] is not None


def test_jobs_retry_failed(client, auth_header, app_fixture):
    """Test retrying a failed job."""
    # Create a job via API first
    r = client.post("/jobs", json={"task_type": "retry_me"}, headers=auth_header)
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    # Manually set the job to FAILED state in the database
    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.FAILED
        job.last_error = "simulated failure"
        job.attempts = 1
        db.session.commit()

    # Now retry it via API
    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 200
    result = r.get_json()
    assert result["status"] == "pending"


def test_jobs_retry_not_failed(client, auth_header):
    """Test that retrying a non-failed job returns 400."""
    r = client.post("/jobs", json={"task_type": "no_retry"}, headers=auth_header)
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    # Job is pending, so retry should fail
    r = client.post(f"/jobs/{job_id}/retry", headers=auth_header)
    assert r.status_code == 400


def test_jobs_stats(client, auth_header):
    """Test job statistics endpoint."""
    payload = {"task_type": "test_stats"}
    r = client.post("/jobs", json=payload, headers=auth_header)
    assert r.status_code == 201

    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    stats = r.get_json()
    assert "total" in stats
    assert stats["total"] >= 1


def test_jobs_list_with_filter(client, auth_header):
    """Test listing jobs with filters."""
    for i in range(3):
        r = client.post("/jobs", json={"task_type": f"task_{i}"}, headers=auth_header)
        assert r.status_code == 201

    r = client.get("/jobs?task_type=task_0", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) == 1


def test_jobs_delete(client, auth_header):
    """Test deleting a job."""
    r = client.post("/jobs", json={"task_type": "to_delete"}, headers=auth_header)
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    r = client.delete(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 404


def test_jobs_dead_letter_queue(client, auth_header, app_fixture):
    """Test dead-letter queue listing."""
    # Create a job
    r = client.post("/jobs", json={"task_type": "dlq_test"}, headers=auth_header)
    assert r.status_code == 201
    job_id = r.get_json()["id"]

    # Move it to DEAD state
    with app_fixture.app_context():
        job = db.session.get(BackgroundJob, job_id)
        job.status = JobStatus.DEAD
        job.last_error = "exceeded max retries"
        job.attempts = 3
        db.session.commit()

    # Check dead-letter queue
    r = client.get("/jobs/dead", headers=auth_header)
    assert r.status_code == 200
    items = r.get_json()
    assert len(items) >= 1
    assert items[0]["status"] == "dead"
