"""Job monitoring API endpoints."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import JobRecord
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("")
@jwt_required()
def list_jobs():
    """List job records for the authenticated user."""
    uid = get_jwt_identity()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status_filter = request.args.get("status", None)

    query = JobRecord.query.filter_by(user_id=uid)
    if status_filter:
        query = query.filter_by(status=status_filter)

    pagination = query.order_by(JobRecord.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return jsonify({
        "jobs": [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "retry_count": j.retry_count,
                "max_retries": j.max_retries,
                "last_error": j.last_error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in pagination.items
        ],
        "total": pagination.total,
        "page": page,
        "per_page": per_page,
    })


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    """Get a specific job record."""
    uid = get_jwt_identity()
    job = JobRecord.query.filter_by(id=job_id, user_id=uid).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404

    return jsonify({
        "id": job.id,
        "job_type": job.job_type,
        "args": job.args,
        "status": job.status,
        "retry_count": job.retry_count,
        "max_retries": job.max_retries,
        "last_error": job.last_error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    })


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Get job execution statistics."""
    uid = get_jwt_identity()
    total = JobRecord.query.filter_by(user_id=uid).count()
    by_status = {}
    for status in ["pending", "running", "completed", "failed", "dead_letter"]:
        count = JobRecord.query.filter_by(user_id=uid, status=status).count()
        if count > 0:
            by_status[status] = count

    return jsonify({
        "total": total,
        "by_status": by_status,
    })
