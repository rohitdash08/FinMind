from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.job_runner import (
    get_job_stats,
    get_recent_jobs,
    get_dead_letter_jobs,
    retry_dead_job,
)
from ..models import BackgroundJob, JobStatus
from ..extensions import db
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("/stats")
@jwt_required()
def job_stats():
    stats = get_job_stats()
    return jsonify(stats)


@bp.get("/recent")
@jwt_required()
def recent_jobs():
    limit = request.args.get("limit", 20, type=int)
    jobs = get_recent_jobs(limit=min(limit, 100))
    return jsonify(jobs)


@bp.get("/dead-letter")
@jwt_required()
def dead_letter_jobs():
    limit = request.args.get("limit", 50, type=int)
    jobs = get_dead_letter_jobs(limit=min(limit, 100))
    return jsonify(jobs)


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify({
        "id": job.id,
        "name": job.name,
        "status": job.status.value,
        "attempts": job.attempts,
        "max_retries": job.max_retries,
        "last_error": job.last_error,
        "result": job.result,
        "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    })


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    result = retry_dead_job(job_id)
    if not result:
        return jsonify(error="Job not found or not in dead state"), 404
    return jsonify(result)
