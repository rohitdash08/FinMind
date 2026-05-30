"""Tests for resilient background job retry & monitoring (issue #130)."""
import time
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_monitor():
    """Return the global monitor after clearing its state for test isolation."""
    from app.services.job_retry import job_monitor
    job_monitor.reset()
    return job_monitor


# ---------------------------------------------------------------------------
# JobMonitor unit tests (no HTTP layer)
# ---------------------------------------------------------------------------

def test_monitor_register_creates_record():
    monitor = _fresh_monitor()
    rec = monitor.register("test_job")
    assert rec.name == "test_job"
    assert rec.status == "idle"
    assert rec.run_count == 0


def test_monitor_register_idempotent():
    monitor = _fresh_monitor()
    r1 = monitor.register("same_job")
    r2 = monitor.register("same_job")
    assert r1 is r2


def test_monitor_all_records():
    monitor = _fresh_monitor()
    monitor.register("job_a")
    monitor.register("job_b")
    names = {r.name for r in monitor.all_records()}
    assert {"job_a", "job_b"} == names


def test_monitor_to_dict_structure():
    monitor = _fresh_monitor()
    monitor.register("j1")
    d = monitor.to_dict()
    assert "j1" in d
    assert "status" in d["j1"]
    assert "run_count" in d["j1"]
    assert "last_error" in d["j1"]


# ---------------------------------------------------------------------------
# retryable decorator unit tests
# ---------------------------------------------------------------------------

def test_retryable_success_on_first_attempt():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()
    calls = []

    @retryable("ok_job", max_retries=2, backoff_base=0)
    def ok_job():
        calls.append(1)
        return "done"

    ok_job()
    assert len(calls) == 1
    rec = monitor.get_record("ok_job")
    assert rec.status == "success"
    assert rec.success_count == 1
    assert rec.failure_count == 0
    assert rec.run_count == 1


def test_retryable_retries_on_failure():
    from app.services.job_retry import retryable
    _fresh_monitor()
    attempts = []

    @retryable("flaky_job", max_retries=2, backoff_base=0)
    def flaky_job():
        attempts.append(1)
        raise RuntimeError("transient error")

    flaky_job()
    assert len(attempts) == 3   # 1 initial + 2 retries


def test_retryable_succeeds_on_second_attempt():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()
    call_count = [0]

    @retryable("recover_job", max_retries=3, backoff_base=0)
    def recover_job():
        call_count[0] += 1
        if call_count[0] < 2:
            raise ValueError("first attempt fails")
        return "recovered"

    recover_job()
    rec = monitor.get_record("recover_job")
    assert rec.status == "success"
    assert rec.success_count == 1
    assert rec.failure_count == 0


def test_retryable_records_failure_after_all_retries():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()

    @retryable("always_fail", max_retries=1, backoff_base=0)
    def always_fail():
        raise RuntimeError("boom")

    always_fail()
    rec = monitor.get_record("always_fail")
    assert rec.status == "failed"
    assert rec.failure_count == 1
    assert rec.success_count == 0
    assert "boom" in rec.last_error


def test_retryable_last_error_cleared_on_success():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()
    should_fail = [True]

    @retryable("toggle_job", max_retries=2, backoff_base=0)
    def toggle_job():
        if should_fail[0]:
            raise RuntimeError("error")

    toggle_job()        # fails, records error
    should_fail[0] = False
    toggle_job()        # succeeds
    rec = monitor.get_record("toggle_job")
    assert rec.status == "success"
    assert rec.last_error is None


def test_retryable_timestamps_updated():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()

    @retryable("ts_job", max_retries=0, backoff_base=0)
    def ts_job():
        pass

    before = datetime.utcnow()
    ts_job()
    after = datetime.utcnow()
    rec = monitor.get_record("ts_job")
    assert rec.last_run is not None
    assert before <= rec.last_run <= after
    assert rec.last_success is not None


def test_retryable_run_count_increments():
    from app.services.job_retry import retryable
    monitor = _fresh_monitor()

    @retryable("count_job", max_retries=0, backoff_base=0)
    def count_job():
        pass

    count_job()
    count_job()
    count_job()
    rec = monitor.get_record("count_job")
    assert rec.run_count == 3


# ---------------------------------------------------------------------------
# HTTP: GET /jobs/status
# ---------------------------------------------------------------------------

def test_job_status_requires_auth(client):
    r = client.get("/jobs/status")
    assert r.status_code == 401


def test_job_status_returns_json(client, auth_header):
    r = client.get("/jobs/status", headers=auth_header)
    assert r.status_code == 200
    data = r.get_json()
    assert "job_count" in data
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


def test_job_status_shows_registered_jobs(client, auth_header):
    from app.services.job_retry import retryable
    _fresh_monitor()

    @retryable("demo_job", max_retries=0, backoff_base=0)
    def demo_job():
        pass

    demo_job()

    r = client.get("/jobs/status", headers=auth_header)
    data = r.get_json()
    job_names = [j["name"] for j in data["jobs"]]
    assert "demo_job" in job_names


def test_job_status_record_structure(client, auth_header):
    from app.services.job_retry import retryable
    _fresh_monitor()

    @retryable("struct_job", max_retries=0, backoff_base=0)
    def struct_job():
        pass

    struct_job()

    r = client.get("/jobs/status", headers=auth_header)
    jobs = {j["name"]: j for j in r.get_json()["jobs"]}
    assert "struct_job" in jobs
    j = jobs["struct_job"]
    for key in ("name", "status", "run_count", "success_count",
                "failure_count", "last_run", "last_success", "last_failure", "last_error"):
        assert key in j, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# HTTP: POST /jobs/trigger/<job_id>  — no scheduler running in tests
# ---------------------------------------------------------------------------

def test_trigger_job_requires_auth(client):
    r = client.post("/jobs/trigger/reminder_dispatch")
    assert r.status_code == 401


def test_trigger_job_503_when_no_scheduler(client, auth_header):
    """In the test environment the scheduler is not started → 503."""
    r = client.post("/jobs/trigger/reminder_dispatch", headers=auth_header)
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Dispatch due reminders job (isolated, no scheduler needed)
# ---------------------------------------------------------------------------

def test_dispatch_job_runs_without_error(client, auth_header, app_fixture):
    """_dispatch_due_reminders_job can run inside an app context without crashing."""
    from app.services.job_retry import _dispatch_due_reminders_job

    with app_fixture.app_context():
        result = _dispatch_due_reminders_job(app_fixture)

    assert "sent" in result
    assert "failed" in result
    assert result["sent"] == 0   # no due reminders in fresh DB
