"""Background job monitoring endpoints."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from ..services.jobs import job_manager
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Return job execution statistics."""
    return jsonify(job_manager.get_stats())


@bp.get("/recent")
@jwt_required()
def recent_jobs():
    """Return recently submitted jobs."""
    return jsonify(job_manager.get_recent_jobs())


@bp.get("/dead-letter")
@jwt_required()
def dead_letter_queue():
    """Return jobs in the dead letter queue."""
    return jsonify(job_manager.get_dead_letter_queue())


@bp.get("/<string:job_id>")
@jwt_required()
def get_job(job_id: str):
    """Return a specific job by ID."""
    job = job_manager.get_job(job_id)
    if not job:
        return jsonify(error="job not found"), 404
    return jsonify(job.to_dict())


@bp.post("/dead-letter/clear")
@jwt_required()
def clear_dead_letter():
    """Clear the dead letter queue."""
    count = job_manager.clear_dead_letter()
    return jsonify(message="dead letter queue cleared", cleared=count)
