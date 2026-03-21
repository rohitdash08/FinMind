import pytest
from app.services.job_retry import (
    create_job,
    execute_job,
    get_job_stats,
    get_dead_letter_jobs,
    get_job_history,
    resilient_job,
)
from app.models import BackgroundJob, JobStatus


def _success_fn():
    return "ok"


def _fail_fn():
    raise ValueError("something went wrong")


_call_count = 0


def _fail_then_succeed():
    global _call_count
    _call_count += 1
    if _call_count < 3:
        raise RuntimeError(f"fail attempt {_call_count}")
    return "recovered"


class TestJobRetryService:
    def test_create_job(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("test-job", max_retries=5)
            assert job.id is not None
            assert job.name == "test-job"
            assert job.status == JobStatus.PENDING.value
            assert job.max_retries == 5
            assert job.attempts == 0

    def test_execute_success(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("success-job")
            result = execute_job(job, _success_fn, base_delay=0.01)
            assert result.status == JobStatus.SUCCESS.value
            assert result.attempts == 1
            assert result.result == "ok"
            assert result.completed_at is not None

    def test_execute_all_retries_exhausted(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("fail-job", max_retries=2)
            result = execute_job(job, _fail_fn, base_delay=0.01)
            assert result.status == JobStatus.DEAD.value
            assert result.attempts == 2
            assert "something went wrong" in result.last_error
            assert result.completed_at is not None

    def test_execute_retry_then_succeed(self, app_fixture):
        global _call_count
        _call_count = 0
        with app_fixture.app_context():
            job = create_job("retry-job", max_retries=5)
            result = execute_job(job, _fail_then_succeed, base_delay=0.01)
            assert result.status == JobStatus.SUCCESS.value
            assert result.attempts == 3
            assert result.result == "recovered"

    def test_job_history_recorded(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("history-job", max_retries=2)
            execute_job(job, _fail_fn, base_delay=0.01)
            history = get_job_history(job.id)
            assert len(history) == 2
            assert history[0]["status"] == JobStatus.RETRYING.value
            assert history[1]["status"] == JobStatus.DEAD.value

    def test_job_stats(self, app_fixture):
        with app_fixture.app_context():
            create_job("stat-1")
            job2 = create_job("stat-2", max_retries=1)
            execute_job(job2, _fail_fn, base_delay=0.01)
            stats = get_job_stats()
            assert stats["total"] >= 2
            assert stats[JobStatus.PENDING.value] >= 1
            assert stats[JobStatus.DEAD.value] >= 1

    def test_dead_letter_queue(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("dead-job", max_retries=1)
            execute_job(job, _fail_fn, base_delay=0.01)
            dead = get_dead_letter_jobs()
            assert len(dead) >= 1
            assert dead[0]["status"] == JobStatus.DEAD.value

    def test_resilient_job_decorator_success(self, app_fixture):
        with app_fixture.app_context():

            @resilient_job(name="decorated-success", max_retries=2, base_delay=0.01)
            def my_task():
                return 42

            result = my_task()
            assert result.status == JobStatus.SUCCESS.value
            assert result.result == "42"

    def test_resilient_job_decorator_failure(self, app_fixture):
        with app_fixture.app_context():

            @resilient_job(name="decorated-fail", max_retries=2, base_delay=0.01)
            def my_bad_task():
                raise RuntimeError("boom")

            result = my_bad_task()
            assert result.status == JobStatus.DEAD.value
            assert "boom" in result.last_error


class TestJobsAPI:
    def test_job_stats_endpoint(self, client, auth_header):
        r = client.get("/jobs/stats", headers=auth_header)
        assert r.status_code == 200
        data = r.get_json()
        assert "total" in data
        assert JobStatus.PENDING.value in data

    def test_list_jobs_empty(self, client, auth_header):
        r = client.get("/jobs", headers=auth_header)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_dead_letter_endpoint(self, client, auth_header):
        r = client.get("/jobs/dead-letter", headers=auth_header)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_get_job_not_found(self, client, auth_header):
        r = client.get("/jobs/99999", headers=auth_header)
        assert r.status_code == 404

    def test_manual_retry(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("retry-api-test", max_retries=1)
            execute_job(job, _fail_fn, base_delay=0.01)
            assert job.status == JobStatus.DEAD.value

            r = client.post(f"/jobs/{job.id}/retry", headers=auth_header)
            assert r.status_code == 200
            data = r.get_json()
            assert data["status"] == JobStatus.PENDING.value
            assert data["attempts"] == 0

    def test_delete_job(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("delete-test")
            r = client.delete(f"/jobs/{job.id}", headers=auth_header)
            assert r.status_code == 200

            r = client.get(f"/jobs/{job.id}", headers=auth_header)
            assert r.status_code == 404

    def test_get_job_with_history(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("history-api-test", max_retries=2)
            execute_job(job, _fail_fn, base_delay=0.01)

            r = client.get(f"/jobs/{job.id}", headers=auth_header)
            assert r.status_code == 200
            data = r.get_json()
            assert data["status"] == JobStatus.DEAD.value
            assert len(data["history"]) == 2

    def test_list_jobs_filter_by_status(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            create_job("filter-pending")
            job2 = create_job("filter-dead", max_retries=1)
            execute_job(job2, _fail_fn, base_delay=0.01)

            r = client.get("/jobs?status=DEAD", headers=auth_header)
            assert r.status_code == 200
            jobs = r.get_json()
            assert all(j["status"] == "DEAD" for j in jobs)
