"""Job monitoring routes."""

from flask import Blueprint, jsonify, request
from app.services.job_retry import get_monitor

bp = Blueprint("jobs", __name__)


@bp.route("/stats", methods=["GET"])
def job_stats():
    """Get job execution statistics."""
    return jsonify(get_monitor().stats())


@bp.route("/recent", methods=["GET"])
def recent_jobs():
    """List recent jobs. Optional ?status=failed&limit=10"""
    limit = request.args.get("limit", 20, type=int)
    status = request.args.get("status")
    return jsonify(get_monitor().recent(limit=limit, status=status))


@bp.route("/dead-letter", methods=["GET"])
def dead_letter():
    """List jobs in dead letter queue."""
    limit = request.args.get("limit", 20, type=int)
    return jsonify(get_monitor().dead_letter_queue(limit=limit))


@bp.route("/<job_id>", methods=["GET"])
def get_job(job_id):
    """Get job details by ID."""
    record = get_monitor().get(job_id)
    if not record:
        return jsonify({"error": "job not found"}), 404
    return jsonify(record.to_dict())
