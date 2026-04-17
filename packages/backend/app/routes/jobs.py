"""Job monitoring and management API endpoints.

Provides REST endpoints to:
- List and filter background jobs
- View individual job status
- Cancel pending jobs
- Retry dead-lettered jobs
- View queue statistics
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.job_queue import (
    get_job_status,
    list_jobs,
    cancel_job,
    retry_dead_job,
    get_queue_stats,
    enqueue,
)

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@jobs_bp.route("", methods=["GET"])
@jwt_required()
def api_list_jobs():
    """List background jobs with optional filters.

    Query params:
        status:   Filter by status (pending|running|completed|failed|retrying|dead)
        job_type: Filter by job type
        queue:    Filter by queue name
        limit:    Max results (default 50)
        offset:   Pagination offset
    """
    status = request.args.get("status")
    job_type = request.args.get("job_type")
    queue = request.args.get("queue")
    limit = request.args.get("limit", 50, type=int)
    offset = request.args.get("offset", 0, type=int)

    jobs = list_jobs(
        status=status,
        job_type=job_type,
        queue=queue,
        limit=min(limit, 200),
        offset=offset,
    )

    # Serialise datetime fields
    for j in jobs:
        for key in ("created_at", "started_at", "completed_at", "next_retry_at"):
            val = j.get(key)
            if val and hasattr(val, "isoformat"):
                j[key] = val.isoformat()

    return jsonify(jobs=jobs, count=len(jobs))


@jobs_bp.route("/<job_id>", methods=["GET"])
@jwt_required()
def api_get_job(job_id):
    """Get detailed status of a single job."""
    job = get_job_status(job_id)
    if job is None:
        return jsonify(error="Job not found"), 404

    for key in ("created_at", "started_at", "completed_at", "next_retry_at"):
        val = job.get(key)
        if val and hasattr(val, "isoformat"):
            job[key] = val.isoformat()

    return jsonify(job)


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
@jwt_required()
def api_cancel_job(job_id):
    """Cancel a pending or retrying job."""
    ok = cancel_job(job_id)
    if not ok:
        return jsonify(error="Cannot cancel job (not found or not in cancellable state)"), 400
    return jsonify(status="cancelled", job_id=job_id)


@jobs_bp.route("/<job_id>/retry", methods=["POST"])
@jwt_required()
def api_retry_job(job_id):
    """Re-enqueue a dead-lettered job for retry."""
    ok = retry_dead_job(job_id)
    if not ok:
        return jsonify(error="Cannot retry job (not found or not dead)"), 400
    return jsonify(status="requeued", job_id=job_id)


@jobs_bp.route("/stats", methods=["GET"])
@jwt_required()
def api_queue_stats():
    """Get aggregate queue statistics."""
    stats = get_queue_stats()
    return jsonify(stats)


@jobs_bp.route("/enqueue", methods=["POST"])
@jwt_required()
def api_enqueue():
    """Manually enqueue a new job.

    Body JSON:
        job_type:     str (required)
        payload:      dict (optional)
        queue:        str (default "default")
        priority:     int (default 5)
        max_retries:  int (default 5)
    """
    data = request.get_json(silent=True) or {}
    job_type = data.get("job_type")
    if not job_type:
        return jsonify(error="job_type is required"), 400

    job_id = enqueue(
        job_type=job_type,
        payload=data.get("payload"),
        queue=data.get("queue", "default"),
        priority=data.get("priority", 5),
        max_retries=data.get("max_retries", 5),
    )
    return jsonify(status="enqueued", job_id=job_id), 201
