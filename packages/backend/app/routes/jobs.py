"""Job monitoring and management API endpoints.

Provides visibility into background job execution, dead-letter queue,
retry management, and system health checks.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.job_manager import (
    get_dead_letter_jobs,
    get_health_status,
    get_job_stats,
    retry_dead_letter_job,
    enqueue_job,
    execute_job,
    process_pending_retries,
)
from ..extensions import db
from ..models import JobExecution, JobStatus
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.api")


@bp.get("/status")
@jwt_required()
def job_status():
    """List job executions with optional filters.

    Query params:
        status: filter by status (PENDING, RUNNING, COMPLETED, FAILED, DEAD)
        job_type: filter by job type
        limit: max results (default 50)
        offset: pagination offset (default 0)
    """
    status_filter = request.args.get("status")
    type_filter = request.args.get("job_type")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.session.query(JobExecution)
    if status_filter:
        q = q.filter(JobExecution.status == status_filter)
    if type_filter:
        q = q.filter(JobExecution.job_type == type_filter)

    total = q.count()
    jobs = q.order_by(JobExecution.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify(
        {
            "total": total,
            "offset": offset,
            "limit": limit,
            "jobs": [_serialize_job(j) for j in jobs],
        }
    )


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Aggregate job statistics: success rate, counts by type/status."""
    stats = get_job_stats()
    return jsonify(stats)


@bp.get("/health")
def job_health():
    """Health check for the job processing system.

    No authentication required so external monitors can poll it.
    """
    health = get_health_status()
    status_code = 200 if health["healthy"] else 503
    return jsonify(health), status_code


@bp.get("/dead-letters")
@jwt_required()
def dead_letter_list():
    """List jobs in the dead-letter queue.

    Query params:
        job_type: filter by job type
        limit: max results (default 50)
    """
    job_type = request.args.get("job_type")
    limit = min(int(request.args.get("limit", 50)), 200)
    jobs = get_dead_letter_jobs(job_type=job_type, limit=limit)
    return jsonify(
        {
            "count": len(jobs),
            "jobs": [_serialize_job(j) for j in jobs],
        }
    )


@bp.post("/dead-letters/<int:job_id>/retry")
@jwt_required()
def retry_dead_letter(job_id: int):
    """Reset a dead-letter job for re-execution."""
    job = retry_dead_letter_job(job_id)
    if not job:
        return jsonify(error="Job not found or not in dead-letter queue"), 404
    return jsonify(_serialize_job(job))


@bp.post("/run-retries")
@jwt_required()
def run_retries():
    """Manually trigger processing of pending retries."""
    count = process_pending_retries()
    return jsonify(processed=count)


def _serialize_job(job: JobExecution) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status,
        "payload": job.payload,
        "result": job.result,
        "last_error": job.last_error,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
    }
