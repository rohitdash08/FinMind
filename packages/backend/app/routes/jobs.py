"""REST API routes for background job management.

Endpoints:
  GET  /jobs              - List jobs for the authenticated user
  POST /jobs              - Create (enqueue) a new job
  GET  /jobs/<id>         - Get a single job by ID
  POST /jobs/<id>/retry   - Manually retry a failed/dead job
  GET  /jobs/stats        - Aggregate job status counts
  GET  /jobs/dead-letter  - List dead-letter (permanently failed) jobs
"""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BackgroundJob, JobStatus, JobType
from ..services.job_queue import enqueue_job, retry_job, execute_job
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


@bp.get("")
@jwt_required()
def list_jobs():
    """List all background jobs for the authenticated user."""
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    job_type_filter = request.args.get("job_type")
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("per_page", 50)), 100)

    query = db.session.query(BackgroundJob).filter_by(user_id=uid)
    if status_filter:
        query = query.filter_by(status=status_filter.upper())
    if job_type_filter:
        query = query.filter_by(job_type=job_type_filter.upper())

    total = query.count()
    items = (
        query.order_by(BackgroundJob.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return jsonify(
        {
            "jobs": [j.to_dict() for j in items],
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    )


@bp.post("")
@jwt_required()
def create_job():
    """Enqueue a new background job."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    name = data.get("name")
    job_type = data.get("job_type")
    if not name or not job_type:
        return jsonify(error="name and job_type are required"), 400

    valid_types = {e.value for e in JobType}
    if job_type.upper() not in valid_types:
        return (
            jsonify(error=f"Invalid job_type. Must be one of: {', '.join(sorted(valid_types))}"),
            400,
        )

    payload = data.get("payload", {})
    max_retries = data.get("max_retries", 5)
    if not isinstance(max_retries, int) or max_retries < 0:
        return jsonify(error="max_retries must be a non-negative integer"), 400

    scheduled_at = None
    if data.get("scheduled_at"):
        try:
            scheduled_at = datetime.fromisoformat(data["scheduled_at"])
        except (ValueError, TypeError):
            return jsonify(error="scheduled_at must be a valid ISO datetime"), 400

    job = enqueue_job(
        user_id=uid,
        name=name,
        job_type=job_type.upper(),
        payload=payload if isinstance(payload, dict) else {},
        max_retries=max_retries,
        scheduled_at=scheduled_at,
    )
    logger.info("Created job id=%s type=%s user=%s", job.id, job.job_type, uid)
    return jsonify(job.to_dict()), 201


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get a single job by ID."""
    uid = int(get_jwt_identity())
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(job.to_dict())


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job_route(job_id: int):
    """Manually retry a failed or dead job."""
    uid = int(get_jwt_identity())
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="not found"), 404

    if job.status not in (JobStatus.FAILED.value, JobStatus.DEAD.value):
        return (
            jsonify(error=f"Cannot retry job in status {job.status}"),
            400,
        )

    job = retry_job(job)
    # Execute immediately in-band for manual retries
    execute_job(job)
    logger.info("Manual retry job id=%s, new status=%s", job.id, job.status)
    return jsonify(job.to_dict())


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Get aggregate job status counts for the authenticated user."""
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(BackgroundJob.status, db.func.count(BackgroundJob.id))
        .filter_by(user_id=uid)
        .group_by(BackgroundJob.status)
        .all()
    )
    counts = {status: count for status, count in rows}
    return jsonify(
        {
            "pending": counts.get(JobStatus.PENDING.value, 0),
            "running": counts.get(JobStatus.RUNNING.value, 0),
            "completed": counts.get(JobStatus.COMPLETED.value, 0),
            "failed": counts.get(JobStatus.FAILED.value, 0),
            "dead": counts.get(JobStatus.DEAD.value, 0),
            "total": sum(counts.values()),
        }
    )


@bp.get("/dead-letter")
@jwt_required()
def dead_letter_queue():
    """List all permanently failed (dead) jobs for the authenticated user."""
    uid = int(get_jwt_identity())
    items = (
        db.session.query(BackgroundJob)
        .filter_by(user_id=uid, status=JobStatus.DEAD.value)
        .order_by(BackgroundJob.updated_at.desc())
        .all()
    )
    return jsonify([j.to_dict() for j in items])
