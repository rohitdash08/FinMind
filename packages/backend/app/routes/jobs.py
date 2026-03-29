"""Job monitoring API endpoints.

Provides:
- GET /jobs/          – list recent executions (filterable)
- GET /jobs/stats     – aggregate status counts
- GET /jobs/<job_id>  – single execution detail
- POST /jobs/retry/<id> – manually re-trigger a DEAD job
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..models.job_execution import JobExecution, JobStatus
from ..services.job_retry import (
    get_cached_status,
    get_job_stats,
    get_recent_executions,
)
from ..extensions import db

bp = Blueprint("jobs", __name__)


@bp.get("/")
@jwt_required()
def list_jobs():
    """Return recent job executions with optional filters."""
    limit = request.args.get("limit", 50, type=int)
    status = request.args.get("status", None)
    job_name = request.args.get("job_name", None)
    limit = min(max(limit, 1), 200)

    executions = get_recent_executions(limit=limit, status=status, job_name=job_name)
    return jsonify([e.to_dict() for e in executions]), 200


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Aggregate job status counts for the dashboard."""
    stats = get_job_stats()
    return jsonify(stats), 200


@bp.get("/<string:job_id>")
@jwt_required()
def job_detail(job_id: str):
    """Get detailed info for a specific job execution."""
    # Try Redis cache first for speed
    cached = get_cached_status(job_id)

    # Always fetch full record from DB for detail view
    execution = JobExecution.query.filter_by(job_id=job_id).first()
    if not execution:
        if cached:
            return jsonify(cached), 200
        return jsonify(error="Job not found"), 404

    return jsonify(execution.to_dict()), 200


@bp.post("/retry/<int:execution_id>")
@jwt_required()
def retry_job(execution_id: int):
    """Manually reset a DEAD job to PENDING for re-execution.

    Note: actual re-execution requires the scheduler or a manual trigger;
    this endpoint resets the status so the monitoring dashboard reflects it.
    """
    execution = db.session.get(JobExecution, execution_id)
    if not execution:
        return jsonify(error="Execution not found"), 404
    if execution.status != JobStatus.DEAD:
        return jsonify(error="Only DEAD jobs can be retried"), 400

    execution.status = JobStatus.PENDING
    execution.attempt = 0
    execution.error_message = None
    execution.error_traceback = None
    execution.next_retry_at = None
    db.session.commit()

    return jsonify(execution.to_dict()), 200
