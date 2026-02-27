"""Tests for resilient background job retry & monitoring."""

import pytest
from app.services.job_retry import (
    create_job, start_job, complete_job, fail_job, retry_due_jobs,
    get_job, list_jobs, get_dead_letter_queue, requeue_dead,
    get_logs, get_stats,
)


@pytest.fixture
def app():
    from app import create_app
    from app.config import Settings
    settings = Settings()
    settings.database_url = "sqlite:///:memory:"
    app = create_app(settings)
    with app.app_context():
        from app.extensions import db
        db.create_all()
        yield app


@pytest.fixture
def user(app):
    with app.app_context():
        from app.extensions import db
        from app.models import User
        from werkzeug.security import generate_password_hash
        u = User(email="test@example.com", password_hash=generate_password_hash("pass"))
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def token(app, user):
    with app.app_context():
        from flask_jwt_extended import create_access_token
        return create_access_token(identity=str(user))


@pytest.fixture
def job(app):
    with app.app_context():
        return create_job("Test Job", "email", {"to": "test@example.com"})


class TestCreateJob:
    def test_basic(self, app):
        with app.app_context():
            j = create_job("Send email", "email")
            assert j["status"] == "pending"
            assert j["attempts"] == 0

    def test_with_options(self, app):
        with app.app_context():
            j = create_job("Report", "report", max_retries=5, priority=10)
            assert j["max_retries"] == 5
            assert j["priority"] == 10

    def test_invalid_type(self, app):
        with app.app_context():
            with pytest.raises(ValueError):
                create_job("Bad", "nonexistent")


class TestJobLifecycle:
    def test_start(self, app, job):
        with app.app_context():
            j = start_job(job["id"])
            assert j["status"] == "running"
            assert j["attempts"] == 1

    def test_complete(self, app, job):
        with app.app_context():
            start_job(job["id"])
            j = complete_job(job["id"], "Done", 150)
            assert j["status"] == "completed"

    def test_fail_with_retry(self, app, job):
        with app.app_context():
            start_job(job["id"])
            j = fail_job(job["id"], "Connection timeout", 100)
            assert j["status"] == "failed"
            assert j["next_retry_at"] is not None

    def test_fail_to_dead(self, app):
        with app.app_context():
            j = create_job("Doomed", "email", max_retries=1)
            start_job(j["id"])
            j = fail_job(j["id"], "Error")
            assert j["status"] == "dead"

    def test_start_not_found(self, app):
        with app.app_context():
            with pytest.raises(ValueError):
                start_job(9999)

    def test_start_completed(self, app, job):
        with app.app_context():
            start_job(job["id"])
            complete_job(job["id"])
            with pytest.raises(ValueError):
                start_job(job["id"])


class TestRetry:
    def test_retry_due(self, app):
        with app.app_context():
            j = create_job("Retry me", "email", max_retries=3)
            start_job(j["id"])
            fail_job(j["id"], "Error")
            # Manually set next_retry_at to past
            from app.services.job_retry import BackgroundJob
            from datetime import datetime, timedelta
            bj = BackgroundJob.query.get(j["id"])
            bj.next_retry_at = datetime.utcnow() - timedelta(minutes=1)
            from app.extensions import db
            db.session.commit()
            retried = retry_due_jobs()
            assert len(retried) == 1
            assert retried[0]["status"] == "pending"


class TestDLQ:
    def test_empty(self, app):
        with app.app_context():
            assert get_dead_letter_queue() == []

    def test_with_dead(self, app):
        with app.app_context():
            j = create_job("Dead", "email", max_retries=1)
            start_job(j["id"])
            fail_job(j["id"], "Fatal")
            dlq = get_dead_letter_queue()
            assert len(dlq) == 1

    def test_requeue(self, app):
        with app.app_context():
            j = create_job("Revive", "email", max_retries=1)
            start_job(j["id"])
            fail_job(j["id"], "Fatal")
            r = requeue_dead(j["id"])
            assert r["status"] == "pending"
            assert r["attempts"] == 0

    def test_requeue_not_dead(self, app, job):
        with app.app_context():
            with pytest.raises(ValueError):
                requeue_dead(job["id"])


class TestMonitoring:
    def test_get_job(self, app, job):
        with app.app_context():
            j = get_job(job["id"])
            assert j["name"] == "Test Job"

    def test_get_not_found(self, app):
        with app.app_context():
            assert get_job(9999) is None

    def test_list(self, app, job):
        with app.app_context():
            jobs = list_jobs()
            assert len(jobs) >= 1

    def test_list_filter(self, app, job):
        with app.app_context():
            jobs = list_jobs(status="pending")
            assert all(j["status"] == "pending" for j in jobs)

    def test_logs(self, app, job):
        with app.app_context():
            start_job(job["id"])
            logs = get_logs(job["id"])
            assert len(logs) >= 1

    def test_stats(self, app, job):
        with app.app_context():
            s = get_stats()
            assert s["total"] >= 1
            assert "pending" in s


class TestAPI:
    def test_create(self, app, user, token):
        client = app.test_client()
        resp = client.post("/jobs/", json={"name": "Test", "job_type": "email"},
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 201

    def test_list(self, app, user, token):
        client = app.test_client()
        resp = client.get("/jobs/", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_stats(self, app, user, token):
        client = app.test_client()
        resp = client.get("/jobs/stats", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_dlq(self, app, user, token):
        client = app.test_client()
        resp = client.get("/jobs/dead-letter", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
