"""
Background job API routes.
"""

from datetime import datetime
from typing import Optional

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BackgroundJob, JobStatus
import logging

from ..services import jobs as jobs_service

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("")
@jwt_required()
def list_jobs():
    """List background jobs for the authenticated user."""
    uid = int(get_jwt_identity())
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    status = request.args.get("status", "").strip().upper()
    task_type = request.args.get("task_type", "").strip() or None

    status_enum: Optional[JobStatus] = None
    if status:
        try:
            status_enum = JobStatus(status.lower())
        except ValueError:
            return jsonify(error="invalid status filter"), 400

    items = jobs_service.list_jobs(
        user_id=uid,
        status=status_enum,
        task_type=task_type,
        page=page,
        page_size=page_size,
    )
    logger.info("List jobs user=%s count=%s", uid, len(items))
    return jsonify([jobs_service.job_to_dict(j) for j in items])


@bp.post("")
@jwt_required()
def create_job():
    """Enqueue a new background job."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    task_type = data.get("task_type") or data.get("taskType")
    if not task_type:
        return jsonify(error="task_type required"), 400

    if not isinstance(task_type, str) or len(task_type) > 100:
        return jsonify(error="invalid task_type"), 400

    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        return jsonify(error="payload must be an object"), 400

    max_attempts = data.get("max_attempts") or data.get("maxAttempts")
    if max_attempts is not None:
        try:
            max_attempts = int(max_attempts)
            if max_attempts < 1 or max_attempts > 10:
                return jsonify(error="max_attempts must be between 1 and 10"), 400
        except (ValueError, TypeError):
            return jsonify(error="invalid max_attempts"), 400
    else:
        max_attempts = 3  # Default

    scheduled_for = data.get("scheduled_for") or data.get("scheduledFor")
    scheduled_dt: Optional[datetime] = None
    if scheduled_for:
        try:
            scheduled_dt = datetime.fromisoformat(scheduled_for)
        except ValueError:
            return jsonify(error="invalid scheduled_for date"), 400

    job = jobs_service.enqueue_job(
        user_id=uid,
        task_type=task_type,
        payload=payload,
        max_attempts=max_attempts,
        scheduled_for=scheduled_dt,
    )
    logger.info("Created job id=%s user=%s task=%s", job.id, uid, task_type)
    return jsonify(jobs_service.job_to_dict(job)), 201


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get a specific job by ID."""
    uid = int(get_jwt_identity())
    job = jobs_service.get_job(job_id, user_id=uid)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(jobs_service.job_to_dict(job))


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Retry a failed or dead job."""
    uid = int(get_jwt_identity())
    job = jobs_service.get_job(job_id, user_id=uid)
    if not job:
        return jsonify(error="not found"), 404

    if job.status not in (JobStatus.FAILED, JobStatus.DEAD, JobStatus.RETRYING):
        return jsonify(error="job is not in a retryable state"), 400

    job = jobs_service.mark_pending(job)
    logger.info("Retrying job id=%s user=%s", job.id, uid)
    return jsonify(jobs_service.job_to_dict(job))


@bp.delete("/<int:job_id>")
@jwt_required()
def delete_job(job_id: int):
    """Delete a job."""
    uid = int(get_jwt_identity())
    job = jobs_service.get_job(job_id, user_id=uid)
    if not job:
        return jsonify(error="not found"), 404

    db.session.delete(job)
    db.session.commit()
    logger.info("Deleted job id=%s user=%s", job_id, uid)
    return jsonify(message="deleted")


@bp.get("/dead")
@jwt_required()
def list_dead_jobs():
    """List dead-letter queue jobs_service."""
    uid = int(get_jwt_identity())
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    items = jobs_service.get_dead_jobs(user_id=uid, page=page, page_size=page_size)
    return jsonify([jobs_service.job_to_dict(j) for j in items])


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Get job statistics for the user."""
    uid = int(get_jwt_identity())

    # Use direct query for efficiency
    query = db.session.query(BackgroundJob).filter_by(user_id=uid)
    total = query.count()

    query_pending = query.filter_by(status=JobStatus.PENDING)
    pending = query_pending.count()

    query_running = query.filter_by(status=JobStatus.RUNNING)
    running = query_running.count()

    query_succeeded = query.filter_by(status=JobStatus.SUCCEEDED)
    succeeded = query_succeeded.count()

    query_failed = query.filter(
        BackgroundJob.status.in_([JobStatus.FAILED, JobStatus.RETRYING])
    )
    failed = query_failed.count()

    query_dead = query.filter_by(status=JobStatus.DEAD)
    dead = query_dead.count()

    return jsonify(
        {
            "total": total,
            "pending": pending,
            "running": running,
            "succeeded": succeeded,
            "failed": failed,
            "dead": dead,
        }
    )
