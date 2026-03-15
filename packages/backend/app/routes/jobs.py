"""
Admin API endpoints for background job monitoring and management.

Endpoints:
    GET  /jobs/status         → Scheduler health + reminder stats
    GET  /jobs/failed         → List failed/dead reminders with errors
    POST /jobs/retry-dead     → Reset dead-lettered reminders
    POST /jobs/run            → Manually trigger a processing run
    POST /jobs/pause          → Pause the background scheduler
    POST /jobs/resume         → Resume the background scheduler
"""

from datetime import datetime
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Reminder
from ..services.job_runner import (
    get_job_stats,
    process_due_reminders,
    retry_dead_letters,
)
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("/status")
@jwt_required()
def job_status():
    """Return scheduler status and reminder pipeline statistics."""
    scheduler = current_app.extensions.get("scheduler")
    scheduler_info = {"running": False, "next_run_time": None}

    if scheduler:
        scheduler_info["running"] = scheduler.running
        job = scheduler.get_job("process_due_reminders")
        if job and job.next_run_time:
            scheduler_info["next_run_time"] = job.next_run_time.isoformat()

    stats = get_job_stats()
    return jsonify(scheduler=scheduler_info, stats=stats)


@bp.get("/failed")
@jwt_required()
def list_failed():
    """List failed and dead-lettered reminders with error details."""
    limit = min(int(request.args.get("limit", 50)), 200)
    status_filter = request.args.get("status", "failed,dead").split(",")

    items = (
        db.session.query(Reminder)
        .filter(Reminder.status.in_(status_filter))
        .order_by(Reminder.id.desc())
        .limit(limit)
        .all()
    )

    return jsonify([
        {
            "id": r.id,
            "user_id": r.user_id,
            "message": r.message[:100],
            "channel": r.channel,
            "status": r.status,
            "retry_count": r.retry_count,
            "last_error": r.last_error,
            "send_at": r.send_at.isoformat() if r.send_at else None,
            "next_retry_at": r.next_retry_at.isoformat() if r.next_retry_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in items
    ])


@bp.post("/retry-dead")
@jwt_required()
def retry_dead():
    """Reset dead-lettered reminders so they can be re-processed."""
    limit = min(int(request.args.get("limit", 20)), 100)
    count = retry_dead_letters(limit=limit)
    return jsonify(reset=count)


@bp.post("/run")
@jwt_required()
def manual_run():
    """Manually trigger a reminder processing run (admin/debug)."""
    batch_size = min(int(request.args.get("batch_size", 50)), 200)
    result = process_due_reminders(batch_size=batch_size)
    return jsonify(
        processed=result.processed,
        succeeded=result.succeeded,
        failed=result.failed,
        dead_lettered=result.dead_lettered,
        recovered=result.recovered,
        duration_ms=result.duration_ms,
    )


@bp.post("/pause")
@jwt_required()
def pause_scheduler():
    """Pause the background scheduler."""
    scheduler = current_app.extensions.get("scheduler")
    if not scheduler:
        return jsonify(error="scheduler not initialized"), 503
    scheduler.pause()
    logger.info("Scheduler paused by user")
    return jsonify(paused=True)


@bp.post("/resume")
@jwt_required()
def resume_scheduler():
    """Resume the background scheduler."""
    scheduler = current_app.extensions.get("scheduler")
    if not scheduler:
        return jsonify(error="scheduler not initialized"), 503
    scheduler.resume()
    logger.info("Scheduler resumed by user")
    return jsonify(resumed=True)
