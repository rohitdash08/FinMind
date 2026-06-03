"""
Flask routes for async job monitoring (Admin-only).

GET    /api/admin/jobs          — list recent jobs (paginated, filterable)
GET    /api/admin/jobs/<id>     — job detail
POST   /api/admin/jobs/<id>/cancel — cancel a pending/retrying job
POST   /api/admin/jobs/retry    — trigger retry queue processing
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from ..extensions import db
from ..models import User
from .jobs import AsyncJob, JobStatus, process_retry_queue

admin_bp = Blueprint("admin_jobs", __name__, url_prefix="/api/admin")


def _require_admin():
    """Placeholder: real auth middleware should verify admin role."""
    # In production, read the JWT / session and check user.role == "ADMIN"
    pass


@admin_bp.route("/jobs", methods=["GET"])
def list_jobs():
    _require_admin()
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    status_filter = request.args.get("status")
    job_type = request.args.get("job_type")

    q = AsyncJob.query
    if status_filter:
        q = q.filter(AsyncJob.status == status_filter.upper())
    if job_type:
        q = q.filter(AsyncJob.job_type == job_type)

    total = q.count()
    jobs = q.order_by(AsyncJob.created_at.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return jsonify({
        "jobs": [j.to_dict() for j in jobs],
        "total": total,
        "page": page,
        "per_page": per_page,
    }), 200


@admin_bp.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id: int):
    _require_admin()
    job = db.session.get(AsyncJob, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict()), 200


@admin_bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
def cancel_job(job_id: int):
    _require_admin()
    job = db.session.get(AsyncJob, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.status not in (JobStatus.PENDING.value, JobStatus.RETRYING.value):
        return jsonify({"error": f"Cannot cancel job in status {job.status}"}), 400
    job.cancel()
    return jsonify({"message": "Job cancelled", "job": job.to_dict()}), 200


@admin_bp.route("/jobs/retry", methods=["POST"])
def trigger_retry():
    _require_admin()
    count = process_retry_queue(max_jobs=50)
    return jsonify({"message": f"Processed {count} retry-eligible jobs"}), 200


@admin_bp.route("/jobs/stats", methods=["GET"])
def job_stats():
    _require_admin()
    total = AsyncJob.query.count()
    by_status = {}
    for s in JobStatus:
        by_status[s.value] = AsyncJob.query.filter(AsyncJob.status == s.value).count()
    # Avg duration for successful jobs
    avg_row = db.session.query(
        db.func.avg(AsyncJob.duration_ms)
    ).filter(AsyncJob.status == JobStatus.SUCCESS.value).scalar()

    return jsonify({
        "total_jobs": total,
        "by_status": by_status,
        "avg_duration_ms": round(avg_row, 2) if avg_row else None,
    }), 200
