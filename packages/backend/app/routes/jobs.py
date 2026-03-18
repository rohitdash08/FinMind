"""Admin-only routes for background job monitoring and management.

Blueprint: ``jobs_bp`` mounted at ``/jobs``.
All endpoints require JWT auth and ADMIN role.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Role
from ..services.job_queue import job_queue
from ..services.job_monitor import job_monitor
import functools
import logging

jobs_bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.routes.jobs")


def admin_required(fn):
    """Decorator that enforces ADMIN role on top of JWT auth."""

    @functools.wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        uid = int(get_jwt_identity())
        user = db.session.get(User, uid)
        if not user or user.role != Role.ADMIN.value:
            return jsonify(error="admin access required"), 403
        return fn(*args, **kwargs)

    return wrapper


@jobs_bp.get("/status")
@admin_required
def status():
    """Dashboard data: queue depth, active workers, success/fail rates."""
    data = job_monitor.dashboard_status()
    return jsonify(data), 200


@jobs_bp.get("/failed")
@admin_required
def list_failed():
    """List failed and dead-letter jobs with error details."""
    limit = request.args.get("limit", 50, type=int)
    jobs = job_queue.list_failed(limit=limit)
    return jsonify(jobs=jobs, count=len(jobs)), 200


@jobs_bp.post("/retry/<job_id>")
@admin_required
def retry_job(job_id: str):
    """Manually retry a failed or dead-letter job."""
    success = job_queue.retry_job(job_id)
    if not success:
        return jsonify(error="job not found or not in retryable state"), 404
    logger.info("Admin retry job %s by user %s", job_id, get_jwt_identity())
    return jsonify(message="job re-enqueued", job_id=job_id), 200


@jobs_bp.delete("/dead-letter/<job_id>")
@admin_required
def clear_dead_letter(job_id: str):
    """Remove a job from the dead-letter queue."""
    success = job_queue.clear_dead_letter(job_id)
    if not success:
        return jsonify(error="job not found in dead-letter queue"), 404
    logger.info("Admin cleared DLQ job %s by user %s", job_id, get_jwt_identity())
    return jsonify(message="dead-letter entry cleared", job_id=job_id), 200
