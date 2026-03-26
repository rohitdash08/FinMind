"""
Jobs monitoring and management API endpoints.

Provides visibility into background job execution, retry status,
and allows manual retry of failed jobs.
"""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import JobExecution, JobStatus
from ..services.job_scheduler import (
    get_job_stats,
    manually_retry_job,
    retry_pending_jobs,
    execute_job,
    _get_handler,
)

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


@bp.get("/status")
@jwt_required()
def list_jobs():
    """
    List all job executions with optional filtering and pagination.

    Query params:
    - status: filter by job status (PENDING, RUNNING, COMPLETED, FAILED, RETRYING, DEAD)
    - job_type: filter by job type
    - page: page number (default 1)
    - per_page: items per page (default 20, max 100)
    """
    uid = int(get_jwt_identity())

    status_filter = request.args.get("status")
    type_filter = request.args.get("job_type")
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    query = db.session.query(JobExecution).filter_by(user_id=uid)

    if status_filter:
        query = query.filter(JobExecution.status == status_filter.upper())
    if type_filter:
        query = query.filter(JobExecution.job_type == type_filter)

    query = query.order_by(JobExecution.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()

    return jsonify(
        {
            "jobs": [j.to_dict() for j in items],
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "pages": (total + per_page - 1) // per_page if per_page else 0,
            },
        }
    )


@bp.get("/stats")
@jwt_required()
def job_stats():
    """
    Aggregate job execution statistics.

    Returns success rate, average duration, counts by status/type,
    and circuit breaker states.
    """
    stats = get_job_stats()
    return jsonify(stats)


@bp.post("/retry/<int:job_id>")
@jwt_required()
def retry_job(job_id: int):
    """
    Manually retry a failed or dead job.

    Resets retry count and re-executes the job immediately.
    """
    uid = int(get_jwt_identity())

    job = db.session.get(JobExecution, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="Job not found"), 404

    if job.status not in (JobStatus.FAILED.value, JobStatus.DEAD.value):
        return jsonify(
            error=f"Cannot retry job in '{job.status}' status. "
            f"Only FAILED or DEAD jobs can be retried."
        ), 400

    retried = manually_retry_job(job_id)
    if not retried:
        return jsonify(error="Failed to retry job"), 500

    return jsonify(retried.to_dict())


@bp.post("/process-retries")
@jwt_required()
def process_retries():
    """
    Process all jobs that are due for retry.

    This endpoint is designed to be called by a cron scheduler
    or the APScheduler interval trigger.
    """
    results = retry_pending_jobs()
    logger.info(
        "Processed retries: processed=%d succeeded=%d failed=%d",
        results["processed"],
        results["succeeded"],
        results["failed"],
    )
    return jsonify(results)


@bp.get("/health")
def jobs_health():
    """
    Health check endpoint for job processing subsystem.

    Returns the state of circuit breakers and counts of
    stuck/retrying jobs.
    """
    from ..services.job_scheduler import email_breaker, whatsapp_breaker

    stuck_count = (
        db.session.query(JobExecution)
        .filter(JobExecution.status == JobStatus.RUNNING.value)
        .count()
    )
    retrying_count = (
        db.session.query(JobExecution)
        .filter(JobExecution.status == JobStatus.RETRYING.value)
        .count()
    )
    dead_count = (
        db.session.query(JobExecution)
        .filter(JobExecution.status == JobStatus.DEAD.value)
        .count()
    )

    healthy = (
        email_breaker.state != "OPEN"
        and whatsapp_breaker.state != "OPEN"
        and stuck_count == 0
    )

    return jsonify(
        {
            "healthy": healthy,
            "stuck_jobs": stuck_count,
            "retrying_jobs": retrying_count,
            "dead_jobs": dead_count,
            "circuit_breakers": {
                "email": email_breaker.get_status(),
                "whatsapp": whatsapp_breaker.get_status(),
            },
        }
    )


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get detailed information about a specific job."""
    uid = int(get_jwt_identity())
    job = db.session.get(JobExecution, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="Job not found"), 404
    return jsonify(job.to_dict())
