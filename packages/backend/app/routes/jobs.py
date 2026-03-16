"""Background job monitoring endpoints (admin + self-service)."""

import json
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import BackgroundJob, User
from ..services.jobs import enqueue

bp = Blueprint("jobs", __name__)


def _job_json(j: BackgroundJob) -> dict:
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status,
        "attempts": j.attempts,
        "max_attempts": j.max_attempts,
        "last_error": j.last_error,
        "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
        "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "created_at": j.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_jobs():
    """List background jobs (admin: all; users: none – monitoring only)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="admin access required"), 403

    status_filter = request.args.get("status")
    q = BackgroundJob.query
    if status_filter:
        q = q.filter(BackgroundJob.status == status_filter.upper())
    jobs = q.order_by(BackgroundJob.created_at.desc()).limit(100).all()
    return jsonify([_job_json(j) for j in jobs])


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Return aggregate job statistics (admin only)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="admin access required"), 403

    from sqlalchemy import func

    rows = (
        db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
        .group_by(BackgroundJob.status)
        .all()
    )
    stats = {status: count for status, count in rows}
    return jsonify(
        {
            "pending": stats.get("PENDING", 0),
            "running": stats.get("RUNNING", 0),
            "succeeded": stats.get("SUCCEEDED", 0),
            "dead": stats.get("DEAD", 0),
            "total": sum(stats.values()),
        }
    )


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    """Reset a DEAD or FAILED job back to PENDING to allow re-execution (admin only)."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="admin access required"), 403

    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="job not found"), 404
    if job.status not in ("DEAD", "FAILED"):
        return jsonify(error="only DEAD or FAILED jobs can be retried"), 400

    job.status = "PENDING"
    job.attempts = 0
    job.last_error = None
    job.next_run_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_job_json(job))


@bp.post("/enqueue")
@jwt_required()
def enqueue_job():
    """Enqueue a job manually (admin only).

    Body: {"job_type": "send_reminder", "payload": {...}}
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != "ADMIN":
        return jsonify(error="admin access required"), 403

    data = request.get_json(force=True)
    job_type = (data.get("job_type") or "").strip()
    if not job_type:
        return jsonify(error="job_type is required"), 400

    payload = data.get("payload") or {}
    job = enqueue(job_type, payload)
    return jsonify(_job_json(job)), 201
