"""API routes for background job monitoring (#130)."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.job_queue import (
    BackgroundJob, JobStatus, enqueue, process_pending, get_job_stats,
)
from ..extensions import db

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("")
@jwt_required()
def list_jobs():
    """List jobs with optional status filter."""
    status = request.args.get("status")
    q = BackgroundJob.query.order_by(BackgroundJob.created_at.desc())
    if status:
        q = q.filter_by(status=status.upper())
    jobs = q.limit(100).all()
    return jsonify([_serialize(j) for j in jobs])


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Return job queue statistics."""
    return jsonify(get_job_stats())


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(_serialize(job))


@bp.post("/process")
@jwt_required()
def trigger_processing():
    """Manually trigger processing of pending jobs."""
    count = process_pending()
    return jsonify(processed=count)


def _serialize(job: BackgroundJob) -> dict:
    return {
        "id": job.id,
        "name": job.name,
        "payload": job.payload,
        "status": job.status,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "last_error": job.last_error,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }
