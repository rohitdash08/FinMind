"""Tests for background job retry system."""

import pytest
from app.services.jobs import (
    enqueue,
    process_next,
    get_job_status,
    get_queue_stats,
    register_handler,
    RetryPolicy,
    JobStatus,
)


@register_handler("test_success")
def _handle_success(payload):
    pass  # always succeeds


_fail_counter = {"count": 0}


@register_handler("test_fail_then_succeed")
def _handle_fail_then_succeed(payload):
    _fail_counter["count"] += 1
    if _fail_counter["count"] < 3:
        raise RuntimeError("transient error")


@register_handler("test_always_fail")
def _handle_always_fail(payload):
    raise RuntimeError("permanent error")


def test_enqueue_and_process_success():
    job_id = enqueue("test_success", {"key": "value"})
    assert job_id

    status = get_job_status(job_id)
    assert status["status"] == JobStatus.QUEUED

    processed = process_next()
    assert processed is True

    status = get_job_status(job_id)
    assert status["status"] == JobStatus.COMPLETED


def test_retry_on_failure():
    _fail_counter["count"] = 0
    job_id = enqueue(
        "test_fail_then_succeed",
        {},
        retry_policy=RetryPolicy(max_retries=3, base_delay=0.01),
    )

    # First attempt fails, re-queued
    process_next()
    status = get_job_status(job_id)
    assert status["status"] == JobStatus.QUEUED
    assert status["attempt"] == 1

    # Second attempt fails, re-queued
    process_next()
    status = get_job_status(job_id)
    assert status["attempt"] == 2

    # Third attempt succeeds
    process_next()
    status = get_job_status(job_id)
    assert status["status"] == JobStatus.COMPLETED


def test_dead_letter_after_max_retries():
    job_id = enqueue(
        "test_always_fail",
        {},
        retry_policy=RetryPolicy(max_retries=2, base_delay=0.01),
    )

    process_next()  # attempt 1 -> fail -> re-queue
    process_next()  # attempt 2 -> fail -> dead letter

    status = get_job_status(job_id)
    assert status["status"] == JobStatus.DEAD
    assert "permanent error" in status["error"]


def test_queue_stats():
    stats = get_queue_stats()
    assert "queue_length" in stats
    assert "dead_letter_count" in stats
