"""
Monitoring and job management API endpoints.

Provides:
- GET  /jobs/stats     — aggregate job statistics
- GET  /jobs           — list/search job executions
- GET  /jobs/<id>      — single job detail
- POST /jobs/<id>/retry — retry a dead-lettered job
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import JobExecution, JobStatus
from ..services.jobs import (
    RetryPolicy,
    get_job_stats,
    retry_dead_letter,
)

bp = Blueprint("jobs", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    """Return aggregate job execution statistics."""
    return jsonify(get_job_stats()), 200


@bp.get("")
@jwt_required()
def list_jobs():
    """List job executions with optional filtering and pagination."""
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    job_type = request.args.get("job_type")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = db.session.query(JobExecution)

    if status:
        try:
            status_enum = JobStatus(status.upper())
            q = q.filter_by(status=status_enum)
        except ValueError:
            return jsonify(error=f"Invalid status: {status}"), 400

    if job_type:
        from ..models import JobType
        try:
            type_enum = JobType(job_type.upper())
            q = q.filter_by(job_type=type_enum)
        except ValueError:
            return jsonify(error=f"Invalid job_type: {job_type}"), 400

    total = q.count()
    items = q.order_by(JobExecution.created_at.desc()).offset(offset).limit(limit).all()

    return jsonify({
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [j.to_dict() for j in items],
    }), 200


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get a single job execution by ID."""
    job = db.session.get(JobExecution, job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(job.to_dict()), 200


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Retry a dead-lettered job, resetting it to PENDING."""
    job = retry_dead_letter(job_id)
    if job is None:
        return jsonify(error="job not found or not in DEAD state"), 404
    return jsonify(job.to_dict()), 200