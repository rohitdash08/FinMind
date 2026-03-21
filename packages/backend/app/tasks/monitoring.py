"""
Celery task monitoring and metrics collection.
Provides visibility into task execution, retry rates, and failures.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from celery import signals
from celery.events.state import Task as CeleryTask
from prometheus_client import Counter, Histogram, Gauge

from ..extensions import redis_client

logger = logging.getLogger("finmind.tasks.monitoring")

# Prometheus metrics for Celery tasks
task_executions_total = Counter(
    "celery_task_executions_total",
    "Total Celery task executions",
    ["task_name", "status", "queue"]
)

task_execution_duration_seconds = Histogram(
    "celery_task_execution_duration_seconds",
    "Task execution duration in seconds",
    ["task_name"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0)
)

task_retries_total = Counter(
    "celery_task_retries_total",
    "Total task retries",
    ["task_name"]
)

task_failures_total = Counter(
    "celery_task_failures_total",
    "Total task failures",
    ["task_name", "exception_type"]
)

active_tasks_gauge = Gauge(
    "celery_active_tasks",
    "Number of currently active tasks",
    ["task_name"]
)


class TaskMonitor:
    """Monitor Celery task execution and collect metrics."""
    
    def __init__(self):
        self._active_tasks: Dict[str, int] = {}
    
    def record_task_start(self, task_name: str, task_id: str):
        """Record task start."""
        self._active_tasks[task_id] = datetime.now(timezone.utc).timestamp()
        active_tasks_gauge.labels(task_name=task_name).inc()
        
        # Store in Redis for distributed visibility
        redis_client.setex(
            f"task:active:{task_id}",
            3600,  # 1 hour TTL
            json.dumps({
                "task_name": task_name,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
        )
    
    def record_task_success(self, task_name: str, task_id: str, runtime: float):
        """Record successful task completion."""
        self._cleanup_task(task_name, task_id)
        task_executions_total.labels(
            task_name=task_name,
            status="success",
            queue=self._get_task_queue(task_name)
        ).inc()
        task_execution_duration_seconds.labels(task_name=task_name).observe(runtime)
        
        # Store completion record
        redis_client.setex(
            f"task:completed:{task_id}",
            86400,  # 24 hours
            json.dumps({
                "task_name": task_name,
                "status": "success",
                "runtime_seconds": runtime,
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        )
    
    def record_task_failure(
        self, 
        task_name: str, 
        task_id: str, 
        exception: Exception,
        retry_count: int = 0
    ):
        """Record task failure."""
        self._cleanup_task(task_name, task_id)
        exc_type = type(exception).__name__
        
        task_executions_total.labels(
            task_name=task_name,
            status="failure",
            queue=self._get_task_queue(task_name)
        ).inc()
        task_failures_total.labels(
            task_name=task_name,
            exception_type=exc_type
        ).inc()
        
        # Store failure record
        redis_client.setex(
            f"task:failed:{task_id}",
            604800,  # 7 days
            json.dumps({
                "task_name": task_name,
                "status": "failure",
                "exception": exc_type,
                "exception_msg": str(exception),
                "retry_count": retry_count,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            })
        )
    
    def record_task_retry(self, task_name: str, task_id: str, retry_count: int):
        """Record task retry."""
        task_retries_total.labels(task_name=task_name).inc()
        
        redis_client.setex(
            f"task:retry:{task_id}",
            86400,
            json.dumps({
                "task_name": task_name,
                "retry_count": retry_count,
                "retried_at": datetime.now(timezone.utc).isoformat(),
            })
        )
    
    def _cleanup_task(self, task_name: str, task_id: str):
        """Cleanup active task tracking."""
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]
        active_tasks_gauge.labels(task_name=task_name).dec()
        redis_client.delete(f"task:active:{task_id}")
    
    def _get_task_queue(self, task_name: str) -> str:
        """Get queue name for a task."""
        queue_map = {
            "tasks.reminders.send_reminder_task": "high_priority",
            "tasks.reminders.cleanup_old_reminders": "low_priority",
            "tasks.ai.generate_insights_task": "default",
            "tasks.ai.process_expense_receipt_task": "default",
            "tasks.reports.generate_weekly_report_task": "low_priority",
            "tasks.reports.generate_monthly_digest_task": "low_priority",
        }
        return queue_map.get(task_name, "default")


# Global monitor instance
task_monitor = TaskMonitor()


# Celery signal handlers
@signals.task_prerun.connect
def on_task_prerun(sender=None, task_id=None, task=None, **kwargs):
    """Handle task start."""
    if task and task_id:
        task_monitor.record_task_start(task.name, task_id)


@signals.task_postrun.connect
def on_task_postrun(sender=None, task_id=None, task=None, retval=None, **kwargs):
    """Handle task completion."""
    if task and task_id:
        runtime = kwargs.get("runtime", 0)
        task_monitor.record_task_success(task.name, task_id, runtime)


@signals.task_failure.connect
def on_task_failure(sender=None, task_id=None, task=None, exception=None, **kwargs):
    """Handle task failure."""
    if task and task_id:
        retry_count = kwargs.get("einfo", {}).get("retries", 0) if kwargs.get("einfo") else 0
        task_monitor.record_task_failure(
            task.name, task_id, exception or Exception("Unknown"), retry_count
        )


@signals.task_retry.connect
def on_task_retry(sender=None, task_id=None, task=None, **kwargs):
    """Handle task retry."""
    if task and task_id:
        retry_count = kwargs.get("request", {}).retries if kwargs.get("request") else 0
        task_monitor.record_task_retry(task.name, task_id, retry_count)


def get_task_statistics() -> Dict[str, Any]:
    """
    Get aggregate task statistics.
    
    Returns:
        dict with task counts, failure rates, etc.
    """
    # Count active tasks from Redis
    active_keys = redis_client.keys("task:active:*")
    completed_keys = redis_client.keys("task:completed:*")
    failed_keys = redis_client.keys("task:failed:*")
    retry_keys = redis_client.keys("task:retry:*")
    dead_letter_keys = redis_client.keys("dead_letter:*")
    
    return {
        "active_tasks": len(active_keys),
        "completed_24h": len(completed_keys),
        "failed_7d": len(failed_keys),
        "retries_24h": len(retry_keys),
        "dead_letter": len(dead_letter_keys),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def get_dead_letter_items() -> list:
    """
    Get all items in dead letter queue.
    
    Returns:
        List of dead letter items
    """
    items = []
    keys = redis_client.keys("dead_letter:*")
    
    for key in keys:
        data = redis_client.get(key)
        if data:
            try:
                items.append(json.loads(data))
            except json.JSONDecodeError:
                items.append({"key": key, "data": data})
    
    return items


def retry_dead_letter_item(key: str) -> bool:
    """
    Retry a specific dead letter item.
    
    Args:
        key: Redis key of the dead letter item
        
    Returns:
        True if retry was initiated
    """
    data = redis_client.get(key)
    if not data:
        return False
    
    try:
        item = json.loads(data)
        reminder_id = item.get("reminder_id")
        
        if reminder_id:
            # Re-queue the task
            from ..tasks.reminders import send_reminder_task
            send_reminder_task.delay(reminder_id)
            redis_client.delete(key)
            logger.info(f"Retried dead letter item {key}, reminder_id={reminder_id}")
            return True
    except Exception as exc:
        logger.error(f"Failed to retry dead letter item {key}: {exc}")
    
    return False
