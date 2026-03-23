import pytest
from app.services.job_retry import (
    create_job,
    execute_job,
    get_job_stats,
    get_dead_letter_jobs,
    get_job_history,
    retry_failed_jobs,
    resilient_job,
    job_to_dict,
)
from app.models import BackgroundJob, JobStatus


def _success_fn():
    return "ok"


def _fail_fn():
    raise ValueError("something went wrong")


def _make_fail_then_succeed(fail_count: int = 2):
    """Return a callable that fails *fail_count* times then succeeds.

    Uses a mutable list instead of a global counter so tests are
    isolated even when run in parallel.
    """
    state = {"calls": 0}

    def _inner():
        state["calls"] += 1
        if state["calls"] <= fail_count:
            raise RuntimeError(f"fail attempt {state['calls']}")
        return "recovered"

    return _inner


# ---------------------------------------------------------------------------
# Service-layer tests
# ---------------------------------------------------------------------------

class TestCreateJob:
    def test_basic(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("test-job", max_retries=5)
            assert job.id is not None
            assert job.name == "test-job"
            assert job.status == JobStatus.PENDING.value
            assert job.max_retries == 5
            assert job.attempts == 0

    def test_name_is_trimmed_and_truncated(self, app_fixture):
        with app_fixture.app_context():
            long_name = "x" * 300
            job = create_job(f"  {long_name}  ", max_retries=2)
            assert len(job.name) == 200
            assert not job.name.startswith(" ")

    def test_empty_name_raises(self, app_fixture):
        with app_fixture.app_context():
            with pytest.raises(ValueError, match="name must not be empty"):
                create_job("   ")

    def test_max_retries_clamped_low(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("clamp-low", max_retries=-5)
            assert job.max_retries == 1

    def test_max_retries_clamped_high(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("clamp-high", max_retries=9999)
            assert job.max_retries == 20


class TestExecuteJob:
    def test_success(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("success-job")
            result = execute_job(job, _success_fn, base_delay=0.01)
            assert result.status == JobStatus.SUCCESS.value
            assert result.attempts == 1
            assert result.result == "ok"
            assert result.completed_at is not None
            assert result.last_error is None

    def test_all_retries_exhausted(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("fail-job", max_retries=2)
            result = execute_job(job, _fail_fn, base_delay=0.01)
            assert result.status == JobStatus.DEAD.value
            assert result.attempts == 2
            assert "something went wrong" in result.last_error
            assert result.completed_at is not None

    def test_retry_then_succeed(self, app_fixture):
        with app_fixture.app_context():
            fn = _make_fail_then_succeed(fail_count=2)
            job = create_job("retry-job", max_retries=5)
            result = execute_job(job, fn, base_delay=0.01)
            assert result.status == JobStatus.SUCCESS.value
            assert result.attempts == 3
            assert result.result == "recovered"

    def test_result_truncated(self, app_fixture):
        """Large results are truncated to 10 000 chars."""
        with app_fixture.app_context():
            big = "z" * 20_000

            def _big_result():
                return big

            job = create_job("big-result")
            result = execute_job(job, _big_result, base_delay=0.01)
            assert len(result.result) == 10_000

    def test_error_truncated(self, app_fixture):
        """Large error messages are truncated to 5 000 chars."""
        with app_fixture.app_context():
            big_msg = "e" * 10_000

            def _big_error():
                raise RuntimeError(big_msg)

            job = create_job("big-err", max_retries=1)
            result = execute_job(job, _big_error, base_delay=0.01)
            assert len(result.last_error) <= 5_000

    def test_max_delay_caps_backoff(self, app_fixture):
        """With max_delay=0.02 the actual sleep should never exceed that."""
        with app_fixture.app_context():
            fn = _make_fail_then_succeed(fail_count=3)
            job = create_job("capped-delay", max_retries=5)
            # backoff would be 1 * 2^2 = 4 on 3rd attempt, but max_delay caps it
            result = execute_job(
                job, fn,
                base_delay=0.01,
                backoff_factor=2.0,
                max_delay=0.02,
            )
            assert result.status == JobStatus.SUCCESS.value

    def test_func_receives_args_and_kwargs(self, app_fixture):
        with app_fixture.app_context():
            def _add(a, b, extra=0):
                return a + b + extra

            job = create_job("args-test")
            result = execute_job(job, _add, 1, 2, base_delay=0.01, extra=10)
            assert result.result == "13"


class TestJobHistory:
    def test_history_recorded_on_failure(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("history-job", max_retries=2)
            execute_job(job, _fail_fn, base_delay=0.01)
            history = get_job_history(job.id)
            assert len(history) == 2
            assert history[0]["status"] == JobStatus.RETRYING.value
            assert history[1]["status"] == JobStatus.DEAD.value

    def test_history_recorded_on_success(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("history-ok")
            execute_job(job, _success_fn, base_delay=0.01)
            history = get_job_history(job.id)
            assert len(history) == 1
            assert history[0]["status"] == JobStatus.SUCCESS.value
            assert history[0]["error"] is None


class TestJobStats:
    def test_stats_include_all_statuses(self, app_fixture):
        with app_fixture.app_context():
            create_job("stat-1")
            job2 = create_job("stat-2", max_retries=1)
            execute_job(job2, _fail_fn, base_delay=0.01)
            stats = get_job_stats()
            assert stats["total"] >= 2
            assert stats[JobStatus.PENDING.value] >= 1
            assert stats[JobStatus.DEAD.value] >= 1
            # Every JobStatus enum member should be present
            for s in JobStatus:
                assert s.value in stats


class TestDeadLetterQueue:
    def test_returns_dead_jobs(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("dead-job", max_retries=1)
            execute_job(job, _fail_fn, base_delay=0.01)
            dead = get_dead_letter_jobs()
            assert len(dead) >= 1
            assert dead[0]["status"] == JobStatus.DEAD.value

    def test_limit_respected(self, app_fixture):
        with app_fixture.app_context():
            for i in range(5):
                j = create_job(f"dead-{i}", max_retries=1)
                execute_job(j, _fail_fn, base_delay=0.01)
            dead = get_dead_letter_jobs(limit=2)
            assert len(dead) == 2


class TestRetryFailedJobs:
    def test_returns_eligible_ids(self, app_fixture):
        with app_fixture.app_context():
            from app.extensions import db as _db

            job = create_job("retryable", max_retries=5)
            # Manually set up a RETRYING state with remaining attempts
            job.status = JobStatus.RETRYING.value
            job.attempts = 2
            job.next_retry_at = None
            _db.session.commit()

            ids = retry_failed_jobs()
            assert job.id in ids

    def test_excludes_exhausted_jobs(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("exhausted", max_retries=1)
            execute_job(job, _fail_fn, base_delay=0.01)
            # Job is now DEAD with attempts == max_retries
            ids = retry_failed_jobs()
            assert job.id not in ids


class TestResilientJobDecorator:
    def test_success(self, app_fixture):
        with app_fixture.app_context():

            @resilient_job(name="decorated-success", max_retries=2, base_delay=0.01)
            def my_task():
                return 42

            result = my_task()
            assert result.status == JobStatus.SUCCESS.value
            assert result.result == "42"

    def test_failure(self, app_fixture):
        with app_fixture.app_context():

            @resilient_job(name="decorated-fail", max_retries=2, base_delay=0.01)
            def my_bad_task():
                raise RuntimeError("boom")

            result = my_bad_task()
            assert result.status == JobStatus.DEAD.value
            assert "boom" in result.last_error

    def test_custom_backoff(self, app_fixture):
        with app_fixture.app_context():

            @resilient_job(
                name="custom-backoff",
                max_retries=3,
                base_delay=0.01,
                backoff_factor=1.5,
                max_delay=0.05,
            )
            def my_task():
                return "done"

            result = my_task()
            assert result.status == JobStatus.SUCCESS.value


class TestJobToDict:
    def test_all_fields_present(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("dict-test")
            d = job_to_dict(job)
            expected_keys = {
                "id", "name", "status", "attempts", "max_retries",
                "last_error", "result", "created_at", "started_at",
                "completed_at", "next_retry_at",
            }
            assert set(d.keys()) == expected_keys

    def test_datetime_fields_are_iso(self, app_fixture):
        with app_fixture.app_context():
            job = create_job("iso-test")
            execute_job(job, _success_fn, base_delay=0.01)
            d = job_to_dict(job)
            # Should be parseable ISO strings
            from datetime import datetime
            datetime.fromisoformat(d["created_at"])
            datetime.fromisoformat(d["started_at"])
            datetime.fromisoformat(d["completed_at"])


# ---------------------------------------------------------------------------
# API / route tests
# ---------------------------------------------------------------------------

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

    def test_list_jobs_invalid_status(self, client, auth_header):
        r = client.get("/jobs?status=BOGUS", headers=auth_header)
        assert r.status_code == 400
        assert "invalid status" in r.get_json()["error"]

    def test_list_jobs_invalid_pagination(self, client, auth_header):
        r = client.get("/jobs?page=abc", headers=auth_header)
        assert r.status_code == 400
        assert "invalid pagination" in r.get_json()["error"]

    def test_dead_letter_endpoint(self, client, auth_header):
        r = client.get("/jobs/dead-letter", headers=auth_header)
        assert r.status_code == 200
        assert isinstance(r.get_json(), list)

    def test_dead_letter_invalid_limit(self, client, auth_header):
        r = client.get("/jobs/dead-letter?limit=abc", headers=auth_header)
        assert r.status_code == 400

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

    def test_manual_retry_records_history(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("retry-hist", max_retries=1)
            execute_job(job, _fail_fn, base_delay=0.01)

            client.post(f"/jobs/{job.id}/retry", headers=auth_header)
            r = client.get(f"/jobs/{job.id}", headers=auth_header)
            data = r.get_json()
            statuses = [h["status"] for h in data["history"]]
            assert "MANUAL_RETRY" in statuses

    def test_manual_retry_not_failed(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("not-failed")
            r = client.post(f"/jobs/{job.id}/retry", headers=auth_header)
            assert r.status_code == 400
            assert "not in a failed state" in r.get_json()["error"]

    def test_manual_retry_not_found(self, client, auth_header):
        r = client.post("/jobs/99999/retry", headers=auth_header)
        assert r.status_code == 404

    def test_delete_job(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            job = create_job("delete-test")
            r = client.delete(f"/jobs/{job.id}", headers=auth_header)
            assert r.status_code == 200

            r = client.get(f"/jobs/{job.id}", headers=auth_header)
            assert r.status_code == 404

    def test_delete_job_not_found(self, client, auth_header):
        r = client.delete("/jobs/99999", headers=auth_header)
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

    def test_list_jobs_pagination(self, app_fixture, client, auth_header):
        with app_fixture.app_context():
            for i in range(5):
                create_job(f"page-test-{i}")

            r = client.get("/jobs?page=1&page_size=2", headers=auth_header)
            assert r.status_code == 200
            page1 = r.get_json()
            assert len(page1) == 2

            r = client.get("/jobs?page=2&page_size=2", headers=auth_header)
            assert r.status_code == 200
            page2 = r.get_json()
            assert len(page2) == 2

            # Pages should not overlap
            ids_1 = {j["id"] for j in page1}
            ids_2 = {j["id"] for j in page2}
            assert ids_1.isdisjoint(ids_2)

    def test_unauthenticated_returns_401(self, client):
        for url in ["/jobs", "/jobs/stats", "/jobs/dead-letter", "/jobs/1"]:
            r = client.get(url)
            assert r.status_code in (401, 422), f"GET {url} should require auth"
        r = client.post("/jobs/1/retry")
        assert r.status_code in (401, 422)
        r = client.delete("/jobs/1")
        assert r.status_code in (401, 422)
