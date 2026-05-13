import logging
import time
from dataclasses import dataclass
from typing import Callable

from flask import current_app

from ..observability import track_background_job_event


@dataclass(frozen=True)
class JobResult:
    success: bool
    attempts: int
    error: str | None = None


def run_with_retry(
    *,
    job_name: str,
    operation: Callable[[], bool],
    max_attempts: int | None = None,
    base_delay_seconds: float | None = None,
    logger: logging.Logger | None = None,
) -> JobResult:
    """Run a boolean job operation with bounded retry and metrics."""
    attempts_limit = max(
        1, int(max_attempts or current_app.config["JOB_RETRY_MAX_ATTEMPTS"])
    )
    delay = float(
        current_app.config["JOB_RETRY_BASE_DELAY_SECONDS"]
        if base_delay_seconds is None
        else base_delay_seconds
    )
    log = logger or logging.getLogger("finmind.jobs")
    last_error = None

    for attempt in range(1, attempts_limit + 1):
        track_background_job_event(job_name, "attempt")
        try:
            if operation():
                track_background_job_event(job_name, "success")
                return JobResult(success=True, attempts=attempt)
            raise RuntimeError("operation returned false")
        except Exception as exc:  # noqa: BLE001 - job runner must isolate failures
            last_error = str(exc) or exc.__class__.__name__
            log.warning(
                "Background job failed job=%s attempt=%s/%s error=%s",
                job_name,
                attempt,
                attempts_limit,
                last_error,
            )
            if attempt < attempts_limit:
                track_background_job_event(job_name, "retry")
                if delay > 0:
                    time.sleep(delay * (2 ** (attempt - 1)))

    track_background_job_event(job_name, "failure")
    return JobResult(success=False, attempts=attempts_limit, error=last_error)
