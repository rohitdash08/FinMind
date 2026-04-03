"""
Job worker process — dequeues and executes jobs with retry handling.
Run as: python -m app.services.worker
"""

import signal
import threading
import sys
import time
import logging
import importlib
from typing import Callable

from ..extensions import redis_client
from .job_queue import dequeue, mark_success, mark_failed, JobStatus

logger = logging.getLogger("finmind.worker")

# Registry of task handlers
_task_registry: dict[str, Callable] = {}
_running = True


def register_task(name: str, handler: Callable) -> None:
    """Register a task handler function."""
    _task_registry[name] = handler
    logger.info("Registered task: %s", name)


def _signal_handler(signum, frame):
    global _running
    logger.info("Received signal %s, shutting down gracefully...", signum)
    _running = False


def run_worker(poll_interval: float = 1.0) -> None:
    """Main worker loop."""
    global _running
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Worker started. Registered tasks: %s", list(_task_registry.keys()))

    while _running:
        try:
            job = dequeue(timeout=poll_interval)
            if not job:
                continue

            task_name = job.get("task_name", "")
            handler = _task_registry.get(task_name)

            if not handler:
                mark_failed(job["id"], f"Unknown task: {task_name}")
                continue

            try:
                # Execute with 30min timeout
                job_timeout = 1800
                handler_result = [None]
                handler_error = [None]
                def _run():
                    try:
                        handler_result[0] = handler(job.get("payload", {}))
                    except Exception as exc:
                        handler_error[0] = exc
                t = threading.Thread(target=_run, daemon=True)
                t.start()
                t.join(timeout=job_timeout)
                if t.is_alive():
                    mark_failed(job["id"], f"Job timed out after {job_timeout}s")
                    continue
                if handler_error[0]:
                    raise handler_error[0]
                result = handler_result[0]
                mark_success(job["id"])
                logger.info("Job %s completed: %s", job["id"], task_name)
            except Exception as e:
                mark_failed(job["id"], str(e))

        except Exception as e:
            logger.error("Worker error: %s", e)
            time.sleep(poll_interval)

    logger.info("Worker shut down.")


# Auto-register example tasks
def _example_send_email(payload: dict) -> str:
    """Example task: send email."""
    logger.info("Sending email to %s: %s", payload.get("to"), payload.get("subject"))
    return "sent"


def _example_generate_report(payload: dict) -> str:
    """Example task: generate report."""
    logger.info("Generating report for user %s", payload.get("user_id"))
    return "generated"


register_task("send_email", _example_send_email)
register_task("generate_report", _example_generate_report)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()

