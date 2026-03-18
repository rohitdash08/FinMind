"""
Background-job monitoring endpoints.

GET  /jobs/status            — scheduler state + registered job list
GET  /jobs/reminders/stats   — counts: sent / pending / overdue / retrying / failed
POST /jobs/reminders/run     — manually trigger due-reminder processing (admin)
"""

from __future__ import annotations

import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import get_jwt, jwt_required

from ..extensions import db
from ..models import Reminder, Role
from ..services.scheduler import get_scheduler, process_due_reminders

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


def _require_admin():
    """Return a 403 response tuple if the caller is not an admin, else None."""
    claims = get_jwt()
    if claims.get("role") != Role.ADMIN.value:
        return jsonify(error="admin required"), 403
    return None


# ---------------------------------------------------------------------------
# GET /jobs/status
# ---------------------------------------------------------------------------

@bp.get("/status")
@jwt_required()
def jobs_status():
    """Return the current scheduler state and the list of registered jobs."""
    scheduler = get_scheduler()

    if scheduler is None or not scheduler.running:
        return jsonify(
            running=False,
            jobs=[],
        )

    jobs_info = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs_info.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": next_run.isoformat() if next_run else None,
                "trigger": str(job.trigger),
            }
        )

    return jsonify(
        running=True,
        jobs=jobs_info,
    )


# ---------------------------------------------------------------------------
# GET /jobs/reminders/stats
# ---------------------------------------------------------------------------

@bp.get("/reminders/stats")
@jwt_required()
def reminders_stats():
    """Return reminder delivery statistics."""
    now = datetime.utcnow()

    total = db.session.query(Reminder).count()
    sent = db.session.query(Reminder).filter(Reminder.sent.is_(True)).count()
    permanently_failed = (
        db.session.query(Reminder).filter(Reminder.failed.is_(True)).count()
    )
    retrying = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            Reminder.retry_count > 0,
        )
        .count()
    )
    overdue = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            Reminder.retry_count == 0,
            Reminder.send_at <= now,
        )
        .count()
    )
    pending = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            Reminder.retry_count == 0,
            Reminder.send_at > now,
        )
        .count()
    )

    return jsonify(
        total=total,
        sent=sent,
        pending=pending,
        overdue=overdue,
        retrying=retrying,
        permanently_failed=permanently_failed,
    )


# ---------------------------------------------------------------------------
# POST /jobs/reminders/run
# ---------------------------------------------------------------------------

@bp.post("/reminders/run")
@jwt_required()
def run_reminders():
    """Manually trigger due-reminder processing. Admin only."""
    denied = _require_admin()
    if denied:
        return denied

    logger.info("Manual reminder job trigger by admin")
    try:
        summary = process_due_reminders(current_app._get_current_object())
    except Exception as exc:
        logger.exception("Manual reminder trigger failed")
        return jsonify(error=str(exc)), 500

    return jsonify(summary), 200
