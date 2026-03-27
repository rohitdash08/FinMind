from app.models import BackgroundJob, JobStatus
from app.extensions import db
from app.services.job_runner import (
    with_retry,
    get_job_stats,
    get_recent_jobs,
    get_dead_letter_jobs,
    retry_dead_job,
    _job_to_dict,
)


def test_jobs_stats_empty(client, auth_header):
    r = client.get("/jobs/stats", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert data["total"] == 0
    assert data["success_rate"] == 0.0


def test_jobs_recent_empty(client, auth_header):
    r = client.get("/jobs/recent", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_jobs_dead_letter_empty(client, auth_header):
    r = client.get("/jobs/dead-letter", headers=auth_header)
    assert r.status_code == 200
    assert r.get_json() == []


def test_jobs_get_not_found(client, auth_header):
    r = client.get("/jobs/99999", headers=auth_header)
    assert r.status_code == 404


def test_jobs_retry_not_found(client, auth_header):
    r = client.post("/jobs/99999/retry", headers=auth_header)
    assert r.status_code == 404


def test_job_model_creation(app_fixture):
    with app_fixture.app_context():
        job = BackgroundJob(
            name="test_job",
            status=JobStatus.PENDING,
            max_retries=3,
        )
        db.session.add(job)
        db.session.commit()

        assert job.id is not None
        assert job.name == "test_job"
        assert job.status == JobStatus.PENDING
        assert job.attempts == 0
        assert job.max_retries == 3


def test_job_stats_with_data(app_fixture):
    with app_fixture.app_context():
        db.session.add(BackgroundJob(name="j1", status=JobStatus.SUCCESS))
        db.session.add(BackgroundJob(name="j2", status=JobStatus.SUCCESS))
        db.session.add(BackgroundJob(name="j3", status=JobStatus.FAILED))
        db.session.add(BackgroundJob(name="j4", status=JobStatus.DEAD))
        db.session.commit()

        stats = get_job_stats()
        assert stats["total"] == 4
        assert stats["by_status"]["SUCCESS"] == 2
        assert stats["by_status"]["FAILED"] == 1
        assert stats["by_status"]["DEAD"] == 1
        assert stats["success_rate"] == 50.0


def test_recent_jobs(app_fixture):
    with app_fixture.app_context():
        for i in range(5):
            db.session.add(BackgroundJob(name=f"job_{i}", status=JobStatus.SUCCESS))
        db.session.commit()

        jobs = get_recent_jobs(limit=3)
        assert len(jobs) == 3


def test_dead_letter_jobs(app_fixture):
    with app_fixture.app_context():
        db.session.add(BackgroundJob(name="alive", status=JobStatus.SUCCESS))
        db.session.add(BackgroundJob(name="dead1", status=JobStatus.DEAD))
        db.session.add(BackgroundJob(name="dead2", status=JobStatus.DEAD))
        db.session.commit()

        dead = get_dead_letter_jobs()
        assert len(dead) == 2
        assert all(j["status"] == "DEAD" for j in dead)


def test_retry_dead_job(app_fixture):
    with app_fixture.app_context():
        job = BackgroundJob(
            name="retry_me",
            status=JobStatus.DEAD,
            attempts=4,
            last_error="connection timeout",
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

        result = retry_dead_job(job_id)
        assert result is not None
        assert result["status"] == "PENDING"
        assert result["attempts"] == 0
        assert result["last_error"] is None


def test_retry_non_dead_job_returns_none(app_fixture):
    with app_fixture.app_context():
        job = BackgroundJob(name="running_job", status=JobStatus.RUNNING)
        db.session.add(job)
        db.session.commit()

        result = retry_dead_job(job.id)
        assert result is None


def test_with_retry_decorator_success(app_fixture):
    with app_fixture.app_context():

        @with_retry("add_numbers", max_retries=2)
        def add(a, b):
            return a + b

        result = add(3, 4)
        assert result == 7

        jobs = get_recent_jobs(limit=1)
        assert len(jobs) == 1
        assert jobs[0]["name"] == "add_numbers"
        assert jobs[0]["status"] == "SUCCESS"
        assert jobs[0]["attempts"] == 1


def test_with_retry_decorator_failure_then_dead(app_fixture):
    with app_fixture.app_context():
        call_count = {"n": 0}

        @with_retry("always_fail", max_retries=2, base_delay=0.01)
        def fail_job():
            call_count["n"] += 1
            raise ValueError("boom")

        result = fail_job()
        assert result is None
        assert call_count["n"] == 3  # 1 initial + 2 retries

        dead = get_dead_letter_jobs()
        assert len(dead) == 1
        assert dead[0]["name"] == "always_fail"
        assert dead[0]["status"] == "DEAD"


def test_with_retry_decorator_eventual_success(app_fixture):
    with app_fixture.app_context():
        call_count = {"n": 0}

        @with_retry("flaky_job", max_retries=3, base_delay=0.01)
        def flaky():
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("not yet")
            return "done"

        result = flaky()
        assert result == "done"
        assert call_count["n"] == 3

        jobs = get_recent_jobs(limit=1)
        assert jobs[0]["status"] == "SUCCESS"
        assert jobs[0]["attempts"] == 3


def test_job_to_dict(app_fixture):
    with app_fixture.app_context():
        job = BackgroundJob(
            name="dict_test",
            status=JobStatus.SUCCESS,
            attempts=1,
            max_retries=3,
        )
        db.session.add(job)
        db.session.commit()

        d = _job_to_dict(job)
        assert d["name"] == "dict_test"
        assert d["status"] == "SUCCESS"
        assert "id" in d
        assert "created_at" in d
