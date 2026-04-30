import json
from datetime import datetime, timedelta
from unittest.mock import patch

from app.extensions import db
from app.models import BackgroundJob, JobStatus, JobType, Reminder
from app.services.jobs import (
    BACKOFF_INTERVALS,
    cleanup_old_jobs,
    enqueue_job,
    execute_job,
    get_job_stats,
    get_job_status,
    process_pending_jobs,
)


def test_enqueue_job_creates_pending_job(app_fixture, auth_header, client):
    with app_fixture.app_context():
        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": 42},
            max_attempts=3,
        )
        assert job.id is not None
        assert job.status == JobStatus.PENDING.value
        assert job.job_type == JobType.REMINDER.value
        assert job.attempts == 0
        assert job.max_attempts == 3
        assert json.loads(job.payload) == {"reminder_id": 42}
        assert job.next_retry_at is not None


def test_enqueue_job_defaults(app_fixture, auth_header, client):
    with app_fixture.app_context():
        job = enqueue_job(user_id=1, job_type=JobType.DIGEST.value)
        assert job.status == JobStatus.PENDING.value
        assert job.max_attempts == 3
        assert json.loads(job.payload) == {}


def test_get_job_status_returns_details(app_fixture, auth_header, client):
    with app_fixture.app_context():
        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": 1},
        )
        result = get_job_status(job.id)
        assert result is not None
        assert result["id"] == job.id
        assert result["status"] == JobStatus.PENDING.value
        assert result["job_type"] == JobType.REMINDER.value
        assert result["payload"] == {"reminder_id": 1}


def test_get_job_status_returns_none_for_missing(app_fixture, auth_header, client):
    with app_fixture.app_context():
        result = get_job_status(999)
        assert result is None


def test_get_job_stats(app_fixture, auth_header, client):
    with app_fixture.app_context():
        enqueue_job(user_id=1, job_type=JobType.REMINDER.value)
        enqueue_job(user_id=1, job_type=JobType.DIGEST.value)
        stats = get_job_stats()
        assert stats["pending"] == 2
        assert stats["completed"] == 0
        assert stats["failed"] == 0
        assert stats["dead"] == 0
        assert stats["total"] == 2


def test_execute_job_success_with_reminder(app_fixture, auth_header, client):
    with app_fixture.app_context():
        # Create a reminder first
        reminder = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder.id},
        )

        with patch(
            "app.services.jobs.send_reminder", return_value=True
        ):
            result = execute_job(job)

        assert result == "completed"
        assert job.status == JobStatus.COMPLETED.value
        assert job.completed_at is not None
        assert job.attempts == 1
        assert job.last_error is None

        # Reminder should be marked as sent
        db.session.refresh(reminder)
        assert reminder.sent is True


def test_execute_job_failure_with_retry(app_fixture, auth_header, client):
    with app_fixture.app_context():
        reminder = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder.id},
            max_attempts=3,
        )

        with patch(
            "app.services.jobs.send_reminder",
            side_effect=RuntimeError("SMTP down"),
        ):
            result = execute_job(job)

        assert result == "failed"
        assert job.status == JobStatus.FAILED.value
        assert job.attempts == 1
        assert "SMTP down" in job.last_error
        assert job.next_retry_at is not None
        # Verify exponential backoff: first retry is 30s
        expected_min = datetime.utcnow() + timedelta(
            seconds=BACKOFF_INTERVALS[0] - 5
        )
        assert job.next_retry_at >= expected_min


def test_execute_job_dead_letter_after_max_attempts(
    app_fixture, auth_header, client
):
    with app_fixture.app_context():
        reminder = Reminder(
            user_id=1,
            message="Test reminder",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder.id},
            max_attempts=2,
        )

        with patch(
            "app.services.jobs.send_reminder",
            side_effect=RuntimeError("Permanent failure"),
        ):
            # First attempt
            result = execute_job(job)
            assert result == "failed"
            assert job.attempts == 1

            # Second attempt (hits max_attempts)
            result = execute_job(job)
            assert result == "dead"
            assert job.status == JobStatus.DEAD.value
            assert job.attempts == 2


def test_process_pending_jobs(app_fixture, auth_header, client):
    with app_fixture.app_context():
        reminder1 = Reminder(
            user_id=1,
            message="Reminder 1",
            send_at=datetime.utcnow(),
            channel="email",
        )
        reminder2 = Reminder(
            user_id=1,
            message="Reminder 2",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add_all([reminder1, reminder2])
        db.session.commit()

        enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder1.id},
        )
        enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder2.id},
        )

        with patch(
            "app.services.jobs.send_reminder", return_value=True
        ):
            results = process_pending_jobs()

        assert results["processed"] == 2
        assert results["succeeded"] == 2
        assert results["failed"] == 0
        assert results["dead"] == 0


def test_process_pending_jobs_skips_future_retries(
    app_fixture, auth_header, client
):
    with app_fixture.app_context():
        job = enqueue_job(
            user_id=1,
            job_type=JobType.DIGEST.value,
            payload={},
        )
        # Set next_retry_at far in the future
        job.next_retry_at = datetime.utcnow() + timedelta(hours=1)
        job.status = JobStatus.FAILED.value
        db.session.commit()

        results = process_pending_jobs()
        assert results["processed"] == 0


def test_cleanup_old_jobs(app_fixture, auth_header, client):
    with app_fixture.app_context():
        # Create an old completed job
        old_job = enqueue_job(
            user_id=1,
            job_type=JobType.DIGEST.value,
        )
        old_job.status = JobStatus.COMPLETED.value
        old_job.completed_at = datetime.utcnow() - timedelta(days=31)
        db.session.commit()

        # Create a recent completed job
        recent_job = enqueue_job(
            user_id=1,
            job_type=JobType.DIGEST.value,
        )
        recent_job.status = JobStatus.COMPLETED.value
        recent_job.completed_at = datetime.utcnow() - timedelta(days=5)
        db.session.commit()

        deleted = cleanup_old_jobs(days=30)
        assert deleted == 1

        # Recent job should still exist
        assert db.session.get(BackgroundJob, recent_job.id) is not None
        # Old job should be deleted
        assert db.session.get(BackgroundJob, old_job.id) is None


def test_job_stats_endpoint(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "pending" in data
    assert "completed" in data
    assert "failed" in data
    assert "dead" in data
    assert "running" in data
    assert "total" in data


def test_job_detail_endpoint(client, auth_header, app_fixture):
    with app_fixture.app_context():
        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": 1},
        )
        job_id = job.id

    r = client.get(f"/jobs/{job_id}", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["id"] == job_id
    assert data["job_type"] == JobType.REMINDER.value


def test_job_detail_endpoint_not_found(client, auth_header):
    r = client.get("/jobs/99999", headers=auth_header)
    assert r.status_code == 404


def test_job_process_endpoint(client, auth_header):
    r = client.post("/jobs/process", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "processed" in data
    assert "succeeded" in data


def test_job_cleanup_endpoint(client, auth_header):
    r = client.post("/jobs/cleanup", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "deleted" in data


def test_reminders_run_enqueues_jobs(client, auth_header, app_fixture):
    """Verify that POST /reminders/run now enqueues jobs instead of sending."""
    with app_fixture.app_context():
        reminder = Reminder(
            user_id=1,
            message="Due now",
            send_at=datetime.utcnow() - timedelta(minutes=5),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

    r = client.post("/reminders/run", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["enqueued"] == 1

    # Job should exist in DB
    with app_fixture.app_context():
        jobs = db.session.query(BackgroundJob).all()
        assert len(jobs) >= 1
        job = jobs[-1]
        assert job.job_type == JobType.REMINDER.value
        assert json.loads(job.payload)["reminder_id"] is not None


def test_exponential_backoff_intervals(app_fixture, auth_header, client):
    """Verify backoff increases across retries."""
    with app_fixture.app_context():
        reminder = Reminder(
            user_id=1,
            message="Backoff test",
            send_at=datetime.utcnow(),
            channel="email",
        )
        db.session.add(reminder)
        db.session.commit()

        job = enqueue_job(
            user_id=1,
            job_type=JobType.REMINDER.value,
            payload={"reminder_id": reminder.id},
            max_attempts=4,
        )

        retry_intervals = []
        with patch(
            "app.services.jobs.send_reminder",
            side_effect=RuntimeError("fail"),
        ):
            for _ in range(3):
                before = datetime.utcnow()
                execute_job(job)
                retry_delay = (job.next_retry_at - before).total_seconds()
                retry_intervals.append(retry_delay)

        # Each interval should be >= the configured backoff
        assert retry_intervals[0] >= BACKOFF_INTERVALS[0] - 1
        assert retry_intervals[1] >= BACKOFF_INTERVALS[1] - 1
        assert retry_intervals[2] >= BACKOFF_INTERVALS[2] - 1
        # Backoff should increase
        assert retry_intervals[1] > retry_intervals[0]
        assert retry_intervals[2] > retry_intervals[1]


def test_unknown_job_type_fails(app_fixture, auth_header, client):
    with app_fixture.app_context():
        job = enqueue_job(
            user_id=1,
            job_type="UNKNOWN",
            payload={},
            max_attempts=1,
        )
        result = execute_job(job)
        assert result == "dead"
        assert "Unknown job type" in job.last_error
