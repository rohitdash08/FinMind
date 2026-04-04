"""REST endpoints for background job management and monitoring."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.job_manager import (
    enqueue,
    get_job,
    list_jobs,
    dead_letter_jobs,
    job_stats,
    retry_failed_job,
    process_pending_jobs,
    run_job,
    get_registered_types,
    JobStatus,
)
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


def _serialize_job(job) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "payload": job.payload,
        "status": job.status,
        "attempt": job.attempt,
        "max_retries": job.max_retries,
        "error_message": job.error_message,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@bp.get("")
@jwt_required()
def list_all_jobs():
    """List jobs with optional filters: status, job_type, page, per_page."""
    status = request.args.get("status")
    job_type = request.args.get("job_type")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    if status and status not in {s.value for s in JobStatus}:
        return jsonify(error=f"Invalid status: {status}"), 400

    per_page = min(per_page, 100)
    items, total = list_jobs(status=status, job_type=job_type, page=page, per_page=per_page)
    return jsonify(
        jobs=[_serialize_job(j) for j in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@bp.get("/stats")
@jwt_required()
def stats():
    """Return aggregate job counts per status."""
    return jsonify(stats=job_stats())


@bp.get("/dead-letter")
@jwt_required()
def dead_letter():
    """List jobs in the dead-letter queue."""
    page = request.args.get("page", 1, type=int)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    items, total = dead_letter_jobs(page=page, per_page=per_page)
    return jsonify(
        jobs=[_serialize_job(j) for j in items],
        total=total,
        page=page,
        per_page=per_page,
    )


@bp.get("/types")
@jwt_required()
def registered_types():
    """Return list of registered job type names."""
    return jsonify(types=get_registered_types())


@bp.get("/<int:job_id>")
@jwt_required()
def get_single_job(job_id: int):
    """Get a single job by ID."""
    job = get_job(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(_serialize_job(job))


@bp.post("")
@jwt_required()
def create_job():
    """Enqueue a new job.

    Body: { "job_type": "...", "payload": {...}, "max_retries": 5 }
    """
    data = request.get_json() or {}
    job_type = data.get("job_type")
    if not job_type or not isinstance(job_type, str):
        return jsonify(error="job_type is required"), 400

    payload = data.get("payload", {})
    max_retries = data.get("max_retries", 5)
    if not isinstance(max_retries, int) or max_retries < 0:
        return jsonify(error="max_retries must be a non-negative integer"), 400

    job = enqueue(job_type, payload, max_retries=max_retries)
    logger.info("Job enqueued via API id=%s type=%s", job.id, job_type)
    return jsonify(_serialize_job(job)), 201


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Reset a failed/dead job back to PENDING for re-execution."""
    try:
        job = retry_failed_job(job_id)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    logger.info("Job %s retried via API", job_id)
    return jsonify(_serialize_job(job))


@bp.post("/process")
@jwt_required()
def process_jobs():
    """Run all pending/due jobs now (admin trigger)."""
    limit = request.args.get("limit", 50, type=int)
    limit = min(limit, 200)
    results = process_pending_jobs(limit=limit)
    return jsonify(
        processed=len(results),
        jobs=[_serialize_job(j) for j in results],
    )
