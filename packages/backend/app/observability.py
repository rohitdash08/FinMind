import json
import logging
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Response, current_app, g, has_request_context, request
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
    multiprocess,
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": self._request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))

    @staticmethod
    def _request_id() -> str | None:
        if not has_request_context():
            return None
        return getattr(g, "request_id", None)


class Observability:
    def __init__(self) -> None:
        self.multiprocess_enabled = bool(os.getenv("PROMETHEUS_MULTIPROC_DIR"))
        self.registry = (
            None if self.multiprocess_enabled else CollectorRegistry(auto_describe=True)
        )
        self.http_requests_total = Counter(
            "finmind_http_requests_total",
            "Total HTTP requests by endpoint/method/status.",
            ["method", "endpoint", "status_code"],
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "finmind_http_request_duration_seconds",
            "HTTP request duration in seconds by endpoint/method.",
            ["method", "endpoint"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
            registry=self.registry,
        )
        self.reminder_events_total = Counter(
            "finmind_reminder_events_total",
            "Reminder lifecycle events for engagement tracking.",
            ["event", "channel", "status"],
            registry=self.registry,
        )
        self.jobs_total = Counter(
            "finmind_jobs_total",
            "Total background jobs by type and status.",
            ["job_type", "status"],
            registry=self.registry,
        )
        self.job_duration_seconds = Histogram(
            "finmind_job_duration_seconds",
            "Background job execution duration in seconds.",
            ["job_type"],
            buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
            registry=self.registry,
        )
        self.jobs_retry_total = Counter(
            "finmind_jobs_retry_total",
            "Total background job retries by type.",
            ["job_type"],
            registry=self.registry,
        )
        self.jobs_dead_letter_total = Counter(
            "finmind_jobs_dead_letter_total",
            "Total background jobs moved to dead letter by type.",
            ["job_type"],
            registry=self.registry,
        )

    def observe_http_request(
        self, method: str, endpoint: str, status_code: int, duration_seconds: float
    ) -> None:
        status = str(status_code)
        self.http_requests_total.labels(
            method=method, endpoint=endpoint, status_code=status
        ).inc()
        self.http_request_duration_seconds.labels(
            method=method, endpoint=endpoint
        ).observe(duration_seconds)

    def record_reminder_event(
        self, event: str, channel: str, status: str = "ok"
    ) -> None:
        self.reminder_events_total.labels(
            event=event, channel=channel, status=status
        ).inc()

    def record_job_completed(
        self, job_type: str, duration_seconds: float
    ) -> None:
        self.jobs_total.labels(job_type=job_type, status="completed").inc()
        self.job_duration_seconds.labels(job_type=job_type).observe(
            duration_seconds
        )

    def record_job_retry(self, job_type: str) -> None:
        self.jobs_total.labels(job_type=job_type, status="failed").inc()
        self.jobs_retry_total.labels(job_type=job_type).inc()

    def record_job_dead_letter(self, job_type: str) -> None:
        self.jobs_total.labels(job_type=job_type, status="dead").inc()
        self.jobs_dead_letter_total.labels(job_type=job_type).inc()

    def metrics_response(self) -> Response:
        if self.multiprocess_enabled:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            payload = generate_latest(registry)
        else:
            payload = generate_latest(self.registry)
        return Response(payload, mimetype="text/plain; version=0.0.4; charset=utf-8")


def configure_logging(log_level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level, logging.INFO))

    json_handler_present = any(
        isinstance(handler.formatter, JsonLogFormatter)
        for handler in root_logger.handlers
        if getattr(handler, "formatter", None) is not None
    )
    if json_handler_present:
        return

    root_logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root_logger.addHandler(handler)


def init_request_context() -> None:
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    g.request_id = request_id
    g.request_start = time.perf_counter()


def finalize_request(response: Response) -> Response:
    request_id = getattr(g, "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id

    request_start = getattr(g, "request_start", None)
    if request_start is not None:
        elapsed = time.perf_counter() - request_start
        endpoint = request.url_rule.rule if request.url_rule else request.path
        obs = current_app.extensions.get("observability")
        if obs:
            obs.observe_http_request(
                method=request.method,
                endpoint=endpoint,
                status_code=response.status_code,
                duration_seconds=elapsed,
            )
    return response


def track_reminder_event(event: str, channel: str, status: str = "ok") -> None:
    obs = current_app.extensions.get("observability")
    if obs:
        obs.record_reminder_event(event=event, channel=channel, status=status)


def track_job_event(
    job_type: str,
    status: str,
    duration_seconds: float = 0.0,
) -> None:
    obs = current_app.extensions.get("observability")
    if not obs:
        return
    if status == "completed":
        obs.record_job_completed(job_type, duration_seconds)
    elif status == "failed":
        obs.record_job_retry(job_type)
    elif status == "dead":
        obs.record_job_dead_letter(job_type)
