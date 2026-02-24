"""
jobs.py — Background job status and monitoring endpoints.

GET  /jobs/status           — scheduler health + job list
GET  /jobs/history?limit=20 — recent execution log
POST /jobs/<job_id>/run     — trigger a job manually (admin)
"""
import logging
from datetime import datetime

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import JobExecutionLog

bp_jobs = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp_jobs.get("/status")
@jwt_required()
def scheduler_status():
    """Return scheduler health and list of configured jobs."""
    scheduler = current_app.extensions.get("scheduler")
    if not scheduler:
        return jsonify({
            "running": False,
            "reason": "Scheduler not active (testing mode or disabled)",
            "jobs": [],
        })

    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id":           job.id,
            "name":         job.name,
            "next_run_utc": next_run.isoformat() if next_run else None,
        })

    return jsonify({
        "running": scheduler.running,
        "job_count": len(jobs),
        "jobs": jobs,
    })


@bp_jobs.get("/history")
@jwt_required()
def job_history():
    """Return recent job execution log entries."""
    try:
        limit = int(request.args.get("limit", 20))
        limit = max(1, min(100, limit))
    except (ValueError, TypeError):
        limit = 20

    logs = (
        db.session.query(JobExecutionLog)
        .order_by(JobExecutionLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return jsonify([
        {
            "id":                log.id,
            "job_name":          log.job_name,
            "started_at":        log.started_at.isoformat(),
            "finished_at":       log.finished_at.isoformat() if log.finished_at else None,
            "status":            log.status,
            "records_processed": log.records_processed,
            "records_failed":    log.records_failed,
            "error_message":     log.error_message,
            "duration_seconds":  (
                round((log.finished_at - log.started_at).total_seconds(), 1)
                if log.finished_at else None
            ),
        }
        for log in logs
    ])


@bp_jobs.post("/<job_id>/run")
@jwt_required()
def trigger_job(job_id: str):
    """Manually trigger a background job by ID."""
    scheduler = current_app.extensions.get("scheduler")
    if not scheduler or not scheduler.running:
        return jsonify(error="Scheduler is not running"), 503

    job = scheduler.get_job(job_id)
    if not job:
        return jsonify(error=f"Job '{job_id}' not found"), 404

    try:
        scheduler.modify_job(job_id, next_run_time=datetime.utcnow())
        logger.info("Manually triggered job=%s", job_id)
        return jsonify({"message": f"Job '{job_id}' scheduled for immediate execution."})
    except Exception as exc:
        return jsonify(error=str(exc)), 500
