"""Pluggable alerting for failed/dead background jobs.

Ships with:
- Console/log alert (always active)
- Email alert (active when SMTP is configured)
- Webhook alert (active when JOB_ALERT_WEBHOOK_URL env var is set)

Register additional callbacks via ``job_retry.register_alert_callback``.
"""

import json
import logging
import os
from typing import TYPE_CHECKING

import requests

from ..models.job_execution import JobStatus

if TYPE_CHECKING:
    from ..models.job_execution import JobExecution

logger = logging.getLogger("finmind.job_alerts")


def log_alert(execution: "JobExecution"):
    """Always-on: log to application logger."""
    level = logging.ERROR if execution.status == JobStatus.DEAD else logging.WARNING
    logger.log(
        level,
        "JOB ALERT [%s] %s — attempt %d/%d — %s: %s",
        execution.status.value,
        execution.job_name,
        execution.attempt,
        execution.max_retries,
        execution.job_id,
        execution.error_message or "no error message",
    )


def email_alert(execution: "JobExecution"):
    """Send email alert for DEAD jobs when SMTP is configured."""
    if execution.status != JobStatus.DEAD:
        return
    try:
        from .reminders import send_email
        from ..config import Settings

        cfg = Settings()
        if not cfg.smtp_url or not cfg.email_from:
            return
        subject = f"[FinMind] Job DEAD: {execution.job_name}"
        body = (
            f"Job: {execution.job_name}\n"
            f"ID: {execution.job_id}\n"
            f"Attempts: {execution.attempt}/{execution.max_retries}\n"
            f"Error: {execution.error_message}\n\n"
            f"Traceback:\n{execution.error_traceback or 'N/A'}"
        )
        send_email(cfg.email_from, subject, body)
    except Exception:
        logger.debug("Email alert failed for %s", execution.job_id)


def webhook_alert(execution: "JobExecution"):
    """POST to an external webhook URL for DEAD or FAILED jobs."""
    url = os.getenv("JOB_ALERT_WEBHOOK_URL")
    if not url:
        return
    try:
        payload = {
            "event": "job_alert",
            "status": execution.status.value,
            "job_name": execution.job_name,
            "job_id": execution.job_id,
            "attempt": execution.attempt,
            "max_retries": execution.max_retries,
            "error": execution.error_message,
        }
        requests.post(url, json=payload, timeout=5)
    except Exception:
        logger.debug("Webhook alert failed for %s", execution.job_id)


def register_default_alerts():
    """Wire up all built-in alert callbacks."""
    from .job_retry import register_alert_callback

    register_alert_callback(log_alert)
    register_alert_callback(email_alert)
    register_alert_callback(webhook_alert)
