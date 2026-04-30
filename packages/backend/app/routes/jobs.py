import logging
from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required

from ..services.jobs import (
    get_job_stats,
    get_job_status,
    process_pending_jobs,
    cleanup_old_jobs,
)

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


@bp.get("/stats")
@jwt_required()
def job_stats():
    """Return aggregate job statistics for monitoring."""
    stats = get_job_stats()
    logger.info("Job stats requested: %s", stats)
    return jsonify(stats)


@bp.get("/<int:job_id>")
@jwt_required()
def job_detail(job_id: int):
    """Return details for a specific job."""
    job = get_job_status(job_id)
    if not job:
        return jsonify(error="not found"), 404
    return jsonify(job)


@bp.post("/process")
@jwt_required()
def trigger_processing():
    """Manually trigger processing of pending jobs."""
    results = process_pending_jobs()
    logger.info("Manual job processing triggered: %s", results)
    return jsonify(results)


@bp.post("/cleanup")
@jwt_required()
def trigger_cleanup():
    """Remove completed jobs older than 30 days."""
    deleted = cleanup_old_jobs(days=30)
    logger.info("Job cleanup triggered: deleted=%s", deleted)
    return jsonify(deleted=deleted)
