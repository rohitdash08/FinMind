import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from sqlalchemy import func

from ..extensions import db
from ..models import BackgroundJob, JobStatus
from ..services.job_runner import retry_failed_jobs, retry_specific_job

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("")
@jwt_required()
def list_jobs():
    """List the current user's background jobs, with optional ?status= filter."""
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")

    query = db.session.query(BackgroundJob).filter_by(user_id=uid)

    if status_filter:
        try:
            status_enum = JobStatus(status_filter.upper())
            query = query.filter_by(status=status_enum)
        except ValueError:
            return jsonify(error=f"Invalid status: {status_filter}"), 400

    jobs = query.order_by(BackgroundJob.created_at.desc()).all()
    return jsonify([_serialize_job(j) for j in jobs])


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Aggregate job counts by status for the current user."""
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(BackgroundJob.status, func.count(BackgroundJob.id))
        .filter_by(user_id=uid)
        .group_by(BackgroundJob.status)
        .all()
    )
    stats = {row[0].value: row[1] for row in rows}
    return jsonify(stats)


@bp.post("/retry-failed")
@jwt_required()
def retry_all_failed():
    """Manually trigger retry of all eligible retrying jobs for the current user."""
    uid = int(get_jwt_identity())
    # Only retry jobs belonging to this user
    from datetime import datetime

    jobs = (
        db.session.query(BackgroundJob)
        .filter(
            BackgroundJob.user_id == uid,
            BackgroundJob.status == JobStatus.RETRYING,
            BackgroundJob.next_retry_at <= datetime.utcnow(),
        )
        .all()
    )
    for job in jobs:
        retry_specific_job(job)
    return jsonify(retried=len(jobs))


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_one(job_id: int):
    """Manually retry a specific job."""
    uid = int(get_jwt_identity())
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="not found"), 404

    retry_specific_job(job)
    return jsonify(_serialize_job(job))


def _serialize_job(job: BackgroundJob) -> dict:
    return {
        "id": job.id,
        "job_type": job.job_type,
        "status": job.status.value,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "next_retry_at": job.next_retry_at.isoformat() if job.next_retry_at else None,
        "last_error": job.last_error,
        "result": job.result,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }
