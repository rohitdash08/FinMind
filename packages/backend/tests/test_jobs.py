import pytest
from app.services.job_retry import retry_on_failure, get_job_status, JobStatus

def test_retry_decorator_success():
    call_count = [0]

    @retry_on_failure(max_retries=2, retry_delays=[0.01], job_id="test-ok")
    def ok_job():
        call_count[0] += 1
        return "done"

    result = ok_job()
    assert result == "done"
    assert call_count[0] == 1

    status = get_job_status("test-ok")
    assert status["status"] == JobStatus.SUCCESS

def test_retry_decorator_retries():
    call_count = [0]

    @retry_on_failure(max_retries=2, retry_delays=[0.01], job_id="test-retry")
    def flaky_job():
        call_count[0] += 1
        if call_count[0] < 3:
            raise ValueError("not yet")
        return "recovered"

    result = flaky_job()
    assert result == "recovered"
    assert call_count[0] == 3

def test_retry_decorator_dead():
    @retry_on_failure(max_retries=1, retry_delays=[0.01], job_id="test-dead")
    def broken_job():
        raise RuntimeError("always fails")

    result = broken_job()
    assert result is None
    status = get_job_status("test-dead")
    assert status["status"] == JobStatus.DEAD
