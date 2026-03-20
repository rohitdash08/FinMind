"""Monitoring and control endpoints for background jobs."""
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import jwt_required

from ..services.jobs import dispatch_reminders, reminder_stats

bp = Blueprint("jobs", __name__)


@bp.get("/status")
def job_status():
    """Return APScheduler job list and scheduler state (no auth required)."""
    scheduler = current_app.extensions.get("scheduler")
    if scheduler is None:
        return jsonify({"scheduler": "not_configured", "jobs": []})

    running = scheduler.running
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append(
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
        )
    return jsonify({"scheduler": "running" if running else "stopped", "jobs": jobs})


@bp.get("/reminders/stats")
@jwt_required()
def reminders_stats():
    """Return aggregate reminder counts by state."""
    return jsonify(reminder_stats())


@bp.post("/reminders/run")
@jwt_required()
def run_reminders():
    """Trigger dispatch_reminders immediately and return result counts."""
    counts = dispatch_reminders()
    return jsonify(counts), 200
