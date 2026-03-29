"""Tests for the /jobs API endpoints."""

import pytest

from app.extensions import db
from app.models.job_execution import JobExecution, JobStatus


def _seed_jobs(app):
    """Create sample job executions."""
    with app.app_context():
        for i, status in enumerate(
            [JobStatus.SUCCESS, JobStatus.DEAD, JobStatus.RUNNING, JobStatus.SUCCESS]
        ):
            e = JobExecution(
                job_id=f"api_test_{i}",
                job_name="test_job",
                status=status,
                attempt=1 if status == JobStatus.SUCCESS else 3,
                max_retries=3,
                error_message="fail" if status == JobStatus.DEAD else None,
            )
            db.session.add(e)
        db.session.commit()


class TestJobsListEndpoint:
    def test_list_requires_auth(self, client):
        r = client.get("/jobs/")
        assert r.status_code in (401, 422)

    def test_list_returns_jobs(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) == 4

    def test_list_filter_by_status(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/?status=DEAD", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert all(j["status"] == "DEAD" for j in data)

    def test_list_filter_by_job_name(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/?job_name=test_job", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 4

    def test_list_limit(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/?limit=2", headers=auth_header)
        assert r.status_code == 200
        assert len(r.get_json()) == 2


class TestJobsStatsEndpoint:
    def test_stats_requires_auth(self, client):
        r = client.get("/jobs/stats")
        assert r.status_code in (401, 422)

    def test_stats_returns_counts(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 4
        assert data["SUCCESS"] == 2
        assert data["DEAD"] == 1


class TestJobDetailEndpoint:
    def test_detail_found(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        r = client.get("/jobs/api_test_0", headers=auth_header)
        assert r.status_code == 200
        assert r.get_json()["job_id"] == "api_test_0"

    def test_detail_not_found(self, client, auth_header):
        r = client.get("/jobs/nonexistent_xyz", headers=auth_header)
        assert r.status_code == 404


class TestRetryEndpoint:
    def test_retry_dead_job(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        # Find the DEAD job
        with app_fixture.app_context():
            dead = JobExecution.query.filter_by(status=JobStatus.DEAD).first()
            dead_id = dead.id

        r = client.post(f"/jobs/retry/{dead_id}", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert data["status"] == "PENDING"

    def test_retry_non_dead_rejected(self, client, auth_header, app_fixture):
        _seed_jobs(app_fixture)
        with app_fixture.app_context():
            success = JobExecution.query.filter_by(status=JobStatus.SUCCESS).first()
            sid = success.id

        r = client.post(f"/jobs/retry/{sid}", headers=auth_header)
        assert r.status_code == 400

    def test_retry_not_found(self, client, auth_header):
        r = client.post("/jobs/retry/99999", headers=auth_header)
        assert r.status_code == 404
