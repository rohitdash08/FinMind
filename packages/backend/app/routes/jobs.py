import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import db
from ..models import BackgroundJob, JobStatus
from ..services.job_runner import _job_to_dict, job_runner

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Return job statistics: counts by status and recent failures."""
    stats = job_runner.get_job_stats()
    return jsonify(stats)


@bp.get("")
@jwt_required()
def list_jobs():
    """List jobs with pagination, filterable by status and job_type."""
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(200, max(1, int(request.args.get("page_size", "50"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    q = BackgroundJob.query
    status_filter = request.args.get("status")
    job_type_filter = request.args.get("job_type")

    if status_filter:
        q = q.filter(BackgroundJob.status == status_filter)
    if job_type_filter:
        q = q.filter(BackgroundJob.job_type == job_type_filter)

    total = q.count()
    items = (
        q.order_by(BackgroundJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify(
        jobs=[_job_to_dict(j) for j in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get a single job's details."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(_job_to_dict(job))


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Manually retry a dead-lettered job."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    if job.status != JobStatus.DEAD_LETTER.value:
        return jsonify(error="only dead_letter jobs can be retried"), 400

    # Reset for retry
    job.status = JobStatus.PENDING.value
    job.last_error = None
    job.next_retry_at = None
    # Don't reset attempts so we can track total history
    db.session.commit()
    logger.info("Job id=%s manually reset to pending for retry", job.id)

    # Execute immediately
    result = job_runner.execute_job(job.id)
    return jsonify(_job_to_dict(result))


@bp.post("/<int:job_id>/cancel")
@jwt_required()
def cancel_job(job_id: int):
    """Cancel a pending job."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    if job.status != JobStatus.PENDING.value:
        return jsonify(error="only pending jobs can be cancelled"), 400

    job.status = JobStatus.CANCELLED.value
    db.session.commit()
    logger.info("Job id=%s cancelled", job.id)
    return jsonify(_job_to_dict(job))
