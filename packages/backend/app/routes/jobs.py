"""Admin endpoints for background job monitoring and dead-letter management.

Provides visibility into job execution status, retry counts, and the ability
to manually retry dead-lettered jobs. Requires admin role.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BackgroundJob, JobStatus, User, Role
from ..services.jobs import (
    get_job_stats,
    process_due_jobs,
    retry_dead_letter_job,
)
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


def _require_admin():
    """Check that the current user has admin role. Returns user_id or raises."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != Role.ADMIN.value:
        from flask import abort

        abort(403, description="Admin access required")
    return uid


@bp.get("/jobs/stats")
@jwt_required()
def job_stats():
    """Get aggregated job statistics.

    Returns counts by status (PENDING, RUNNING, SUCCESS, FAILED, DEAD_LETTER)
    and by job type.
    """
    _require_admin()
    stats = get_job_stats()
    return jsonify(stats)


@bp.get("/jobs")
@jwt_required()
def list_jobs():
    """List background jobs with optional filters.

    Query params:
        status: Filter by status (PENDING, RUNNING, SUCCESS, FAILED, DEAD_LETTER)
        job_type: Filter by job type
        limit: Max results (default 50, max 200)
        offset: Pagination offset
    """
    _require_admin()

    query = BackgroundJob.query

    status_filter = request.args.get("status")
    if status_filter:
        try:
            query = query.filter(BackgroundJob.status == JobStatus(status_filter))
        except ValueError:
            return jsonify(error=f"Invalid status: {status_filter}"), 400

    job_type_filter = request.args.get("job_type")
    if job_type_filter:
        query = query.filter(BackgroundJob.job_type == job_type_filter)

    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    total = query.count()
    jobs = (
        query.order_by(BackgroundJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return jsonify(
        total=total,
        offset=offset,
        limit=limit,
        jobs=[
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": str(j.status),
                "attempt": j.attempt,
                "max_retries": j.max_retries,
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
                "last_error": j.last_error,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ],
    )


@bp.get("/jobs/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get full details for a specific job."""
    _require_admin()
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="Job not found"), 404

    return jsonify(
        id=job.id,
        job_type=job.job_type,
        payload=job.payload,
        status=str(job.status),
        attempt=job.attempt,
        max_retries=job.max_retries,
        next_run_at=job.next_run_at.isoformat() if job.next_run_at else None,
        last_error=job.last_error,
        result=job.result,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@bp.post("/jobs/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Manually retry a dead-lettered job.

    Resets the job to PENDING status with attempt count reset to 0.
    The job will be picked up on the next processing cycle.
    """
    _require_admin()
    success = retry_dead_letter_job(job_id)
    if not success:
        job = db.session.get(BackgroundJob, job_id)
        if not job:
            return jsonify(error="Job not found"), 404
        return jsonify(error=f"Job is not in DEAD_LETTER status (current: {job.status})"), 400

    return jsonify(status="retried", job_id=job_id)


@bp.post("/jobs/process")
@jwt_required()
def trigger_process():
    """Manually trigger processing of due jobs.

    Useful for testing or when the automatic scheduler is not running.
    """
    _require_admin()
    limit = int(request.args.get("limit", 50))
    stats = process_due_jobs(limit=limit)
    return jsonify(**stats)


@bp.delete("/jobs/<int:job_id>")
@jwt_required()
def delete_job(job_id: int):
    """Delete a job record (admin only)."""
    _require_admin()
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="Job not found"), 404

    db.session.delete(job)
    db.session.commit()
    logger.info("Deleted job id=%s", job_id)
    return jsonify(deleted=True, job_id=job_id)
