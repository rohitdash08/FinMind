"""
REST API endpoints for background job monitoring and management.
GET  /api/jobs        - list jobs with filters
GET  /api/jobs/stats  - aggregate status counts
GET  /api/jobs/<id>   - single job detail
POST /api/jobs/<id>/requeue - requeue a dead job
POST /api/jobs/<id>/cancel  - cancel pending/retrying job
"""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..models import BackgroundJob, JobStatus
from ..services.job_service import (
    cancel_job,
    get_dead_letter_jobs,
    get_job_stats,
    requeue_dead_job,
)

jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


@jobs_bp.get("")
@jwt_required()
def list_jobs():
    """List jobs for the current user with optional status filter."""
    user_id = int(get_jwt_identity())
    status = request.args.get("status")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    query = BackgroundJob.query.filter_by(user_id=user_id)
    if status:
        try:
            JobStatus(status)
        except ValueError:
            return jsonify({"error": f"Invalid status. Valid values: {[s.value for s in JobStatus]}"}), 400
        query = query.filter_by(status=status)

    total = query.count()
    jobs = query.order_by(BackgroundJob.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify({
        "total": total,
        "items": [j.to_dict() for j in jobs],
        "offset": offset,
        "limit": limit,
    })


@jobs_bp.get("/stats")
@jwt_required()
def job_stats():
    """Aggregate job counts per status for the current user."""
    user_id = int(get_jwt_identity())
    stats = get_job_stats(user_id=user_id)
    return jsonify(stats)


@jobs_bp.get("/dead-letter")
@jwt_required()
def dead_letter_queue():
    """Return dead-letter jobs for the current user."""
    user_id = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 100)), 500)
    jobs = get_dead_letter_jobs(user_id=user_id, limit=limit)
    return jsonify({"items": [j.to_dict() for j in jobs], "count": len(jobs)})


@jobs_bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Retrieve a single job by ID (must belong to current user)."""
    user_id = int(get_jwt_identity())
    job = BackgroundJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


@jobs_bp.post("/<int:job_id>/requeue")
@jwt_required()
def requeue_job(job_id: int):
    """Requeue a dead-letter job for retry."""
    user_id = int(get_jwt_identity())
    job = BackgroundJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    result = requeue_dead_job(job_id)
    if not result:
        return jsonify({"error": "Only DEAD jobs can be requeued"}), 400
    return jsonify(result.to_dict())


@jobs_bp.post("/<int:job_id>/cancel")
@jwt_required()
def cancel(job_id: int):
    """Cancel a pending or retrying job."""
    user_id = int(get_jwt_identity())
    job = BackgroundJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    success = cancel_job(job_id)
    if not success:
        return jsonify({"error": "Job cannot be cancelled in its current state"}), 400
    return jsonify(job.to_dict())
