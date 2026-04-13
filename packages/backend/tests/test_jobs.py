import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import BackgroundJob, Bill, Reminder, JobStatus, BillCadence


@pytest.fixture
def auth(client):
    """Register and login, return auth header dict."""
    client.post(
        "/auth/register",
        json={"email": "jobuser@example.com", "password": "pass123"},
    )
    r = client.post(
        "/auth/login",
        json={"email": "jobuser@example.com", "password": "pass123"},
    )
    token = r.get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seed_reminder(client, auth):
    """Create a bill and a reminder for testing."""
    # Create bill
    r = client.post(
        "/bills",
        json={
            "name": "Test Bill",
            "amount": 100,
            "next_due_date": (datetime.utcnow() + timedelta(days=7)).date().isoformat(),
            "cadence": "MONTHLY",
        },
        headers=auth,
    )
    bill_id = r.get_json()["id"]

    # Create reminder that is already due
    r = client.post(
        "/reminders",
        json={
            "bill_id": bill_id,
            "message": "Pay your bill",
            "send_at": (datetime.utcnow() - timedelta(minutes=5)).isoformat(),
            "channel": "email",
        },
        headers=auth,
    )
    return r.get_json()["id"]


def test_list_jobs_empty(client, auth):
    """GET /jobs returns empty list when no jobs exist."""
    r = client.get("/jobs", headers=auth)
    assert r.status_code == 200
    assert r.get_json() == []


def test_run_due_creates_background_jobs(client, auth, seed_reminder):
    """POST /reminders/run creates BackgroundJob records."""
    r = client.post("/reminders/run", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["processed"] == 1

    # Verify job was created
    r = client.get("/jobs", headers=auth)
    assert r.status_code == 200
    jobs = r.get_json()
    assert len(jobs) == 1
    assert jobs[0]["job_type"] == "send_reminder"
    assert jobs[0]["status"] in ("SUCCEEDED", "FAILED", "RETRYING")  # may fail due to no SMTP


def test_job_stats(client, auth, seed_reminder):
    """GET /jobs/stats returns aggregate counts by status."""
    # Create a job via run
    client.post("/reminders/run", headers=auth)

    r = client.get("/jobs/stats", headers=auth)
    assert r.status_code == 200
    stats = r.get_json()
    # Should have at least one entry
    total = sum(stats.values())
    assert total >= 1


def test_list_jobs_with_status_filter(client, auth):
    """GET /jobs?status=FAILED filters correctly."""
    # Insert a FAILED job directly
    with client.application.app_context():
        job = BackgroundJob(
            user_id=1,
            job_type="send_reminder",
            payload=json.dumps({"reminder_id": 999}),
            status=JobStatus.FAILED,
            attempts=3,
            max_attempts=3,
        )
        db.session.add(job)
        db.session.commit()

    r = client.get("/jobs?status=FAILED", headers=auth)
    assert r.status_code == 200
    jobs = r.get_json()
    assert all(j["status"] == "FAILED" for j in jobs)


def test_retry_specific_job(client, auth):
    """POST /jobs/<id>/retry resets and re-executes a failed job."""
    with client.application.app_context():
        job = BackgroundJob(
            user_id=1,
            job_type="send_reminder",
            payload=json.dumps({"reminder_id": 999}),
            status=JobStatus.FAILED,
            attempts=3,
            max_attempts=3,
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    r = client.post(f"/jobs/{job_id}/retry", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    # Should still be FAILED since reminder doesn't exist
    assert data["status"] == "FAILED"


def test_retry_specific_job_not_found(client, auth):
    """POST /jobs/99999/retry returns 404 for nonexistent job."""
    r = client.post("/jobs/99999/retry", headers=auth)
    assert r.status_code == 404


def test_backoff_delay_computation():
    """Verify exponential backoff formula."""
    from app.services.job_runner import compute_backoff_delay

    assert compute_backoff_delay(1) == 60
    assert compute_backoff_delay(2) == 120
    assert compute_backoff_delay(3) == 240
    assert compute_backoff_delay(10) == 300  # capped at 300


def test_retry_all_failed_endpoint(client, auth):
    """POST /jobs/retry-failed retries eligible RETRYING jobs."""
    with client.application.app_context():
        job = BackgroundJob(
            user_id=1,
            job_type="send_reminder",
            payload=json.dumps({"reminder_id": 999}),
            status=JobStatus.RETRYING,
            attempts=1,
            max_attempts=3,
            next_retry_at=datetime.utcnow() - timedelta(seconds=10),
        )
        db.session.add(job)
        db.session.commit()

    r = client.post("/jobs/retry-failed", headers=auth)
    assert r.status_code == 200
    data = r.get_json()
    assert data["retried"] == 1
