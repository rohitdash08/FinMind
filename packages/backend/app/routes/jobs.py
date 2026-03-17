"""
Job monitoring endpoints.

GET /jobs/status  — scheduler health + registered job list
GET /jobs/reminders/stats — reminder delivery stats (sent/pending/retrying/failed)
POST /jobs/reminders/run  — manually trigger the reminder dispatch job (admin/ops use)
"""

from datetime import datetime
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import Reminder
from ..services.scheduler import get_scheduler, process_due_reminders

bp = Blueprint("jobs", __name__)


@bp.get("/status")
@jwt_required()
def scheduler_status():
    scheduler = get_scheduler()
    if scheduler is None or not scheduler.running:
        return jsonify(
            running=False,
            jobs=[],
        )

    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat()
                if job.next_run_time
                else None,
                "trigger": str(job.trigger),
            }
        )

    return jsonify(running=True, jobs=jobs)


@bp.get("/reminders/stats")
@jwt_required()
def reminder_stats():
    now = datetime.utcnow()

    total = db.session.query(Reminder).count()
    sent = db.session.query(Reminder).filter_by(sent=True).count()
    permanently_failed = db.session.query(Reminder).filter_by(failed=True).count()
    retrying = (
        db.session.query(Reminder)
        .filter(
            Reminder.sent.is_(False),
            Reminder.failed.is_(False),
            Reminder.retry_count > 0,
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

    return jsonify(
        total=total,
        sent=sent,
        pending=pending,
        overdue=overdue,
        retrying=retrying,
        permanently_failed=permanently_failed,
    )


@bp.post("/reminders/run")
@jwt_required()
def trigger_reminder_job():
    """Manually trigger reminder dispatch. Useful for ops/debugging."""
    from flask import current_app
    summary = process_due_reminders(app=current_app._get_current_object())
    return jsonify(summary), 200
