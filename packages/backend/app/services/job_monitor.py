"""Job monitoring and observability for the background job queue.

Provides real-time metrics, health status, and alert threshold checks.
Integrates with the existing Observability module for Prometheus metrics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from ..extensions import redis_client
from .job_queue import JobQueue, job_queue

logger = logging.getLogger("finmind.job_monitor")


@dataclass
class AlertThresholds:
    """Configurable alert thresholds for job health monitoring."""

    max_failure_rate: float = 0.25  # 25% failure rate triggers alert
    max_dlq_size: int = 100  # alert if dead-letter queue exceeds this
    max_queue_depth: int = 1000  # alert if pending queue exceeds this
    max_avg_duration: float = 60.0  # alert if avg job duration exceeds (seconds)


DEFAULT_THRESHOLDS = AlertThresholds()


class JobMonitor:
    """Monitoring and observability layer for the job queue."""

    def __init__(self, queue: JobQueue | None = None, thresholds: AlertThresholds | None = None):
        self._queue = queue or job_queue
        self._thresholds = thresholds or DEFAULT_THRESHOLDS

    @property
    def thresholds(self) -> AlertThresholds:
        return self._thresholds

    @thresholds.setter
    def thresholds(self, value: AlertThresholds):
        self._thresholds = value

    def dashboard_status(self) -> dict:
        """Return a comprehensive status snapshot for the admin dashboard."""
        metrics = self._queue.get_metrics()
        queue_depth = self._queue.queue_depth()
        active = self._queue.active_count()
        dlq_size = self._queue.dlq_count()
        completed = self._queue.completed_count()

        succeeded = int(metrics.get("succeeded", 0))
        dead = int(metrics.get("dead", 0))
        retries = int(metrics.get("retries", 0))
        enqueued = int(metrics.get("enqueued", 0))
        manual_retries = int(metrics.get("manual_retries", 0))

        total_duration = float(metrics.get("total_duration", 0))
        duration_count = int(metrics.get("duration_count", 0))
        avg_duration = round(total_duration / duration_count, 3) if duration_count > 0 else 0

        total_completed = succeeded + dead
        success_rate = round(succeeded / total_completed, 4) if total_completed > 0 else 1.0
        failure_rate = round(1 - success_rate, 4)

        alerts = self._check_alerts(
            failure_rate=failure_rate,
            dlq_size=dlq_size,
            queue_depth=queue_depth,
            avg_duration=avg_duration,
        )

        return {
            "queue_depth": queue_depth,
            "active_workers": active,
            "completed": completed,
            "dlq_size": dlq_size,
            "metrics": {
                "enqueued": enqueued,
                "succeeded": succeeded,
                "dead": dead,
                "retries": retries,
                "manual_retries": manual_retries,
                "success_rate": success_rate,
                "failure_rate": failure_rate,
                "avg_duration_seconds": avg_duration,
            },
            "alerts": alerts,
            "timestamp": time.time(),
        }

    def job_execution_metrics(self) -> dict:
        """Return focused execution metrics."""
        metrics = self._queue.get_metrics()
        succeeded = int(metrics.get("succeeded", 0))
        dead = int(metrics.get("dead", 0))
        retries = int(metrics.get("retries", 0))

        total_duration = float(metrics.get("total_duration", 0))
        duration_count = int(metrics.get("duration_count", 0))
        avg_duration = round(total_duration / duration_count, 3) if duration_count > 0 else 0

        total = succeeded + dead
        return {
            "success_rate": round(succeeded / total, 4) if total > 0 else 1.0,
            "failure_rate": round(dead / total, 4) if total > 0 else 0.0,
            "avg_duration_seconds": avg_duration,
            "total_retries": retries,
            "total_succeeded": succeeded,
            "total_dead": dead,
        }

    def queue_counts(self) -> dict:
        """Return current queue state counts."""
        return {
            "pending": self._queue.queue_depth(),
            "active": self._queue.active_count(),
            "completed": self._queue.completed_count(),
            "dead_letter": self._queue.dlq_count(),
        }

    def _check_alerts(
        self,
        failure_rate: float,
        dlq_size: int,
        queue_depth: int,
        avg_duration: float,
    ) -> list[dict]:
        """Check metrics against thresholds and return active alerts."""
        alerts = []
        t = self._thresholds

        if failure_rate > t.max_failure_rate:
            alerts.append({
                "level": "critical",
                "type": "high_failure_rate",
                "message": (
                    f"Failure rate {failure_rate:.1%} exceeds threshold "
                    f"{t.max_failure_rate:.1%}"
                ),
                "value": failure_rate,
                "threshold": t.max_failure_rate,
            })

        if dlq_size > t.max_dlq_size:
            alerts.append({
                "level": "warning",
                "type": "dlq_overflow",
                "message": (
                    f"Dead-letter queue size {dlq_size} exceeds threshold "
                    f"{t.max_dlq_size}"
                ),
                "value": dlq_size,
                "threshold": t.max_dlq_size,
            })

        if queue_depth > t.max_queue_depth:
            alerts.append({
                "level": "warning",
                "type": "queue_backlog",
                "message": (
                    f"Queue depth {queue_depth} exceeds threshold "
                    f"{t.max_queue_depth}"
                ),
                "value": queue_depth,
                "threshold": t.max_queue_depth,
            })

        if avg_duration > t.max_avg_duration:
            alerts.append({
                "level": "warning",
                "type": "slow_jobs",
                "message": (
                    f"Average job duration {avg_duration:.1f}s exceeds threshold "
                    f"{t.max_avg_duration:.1f}s"
                ),
                "value": avg_duration,
                "threshold": t.max_avg_duration,
            })

        return alerts


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
job_monitor = JobMonitor()
