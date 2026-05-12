"""Job monitoring routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.jobs import get_queue_stats, get_dead_letter_jobs, get_job_status, retry_dead_letter_job

bp = Blueprint("jobs", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    return jsonify(get_queue_stats())


@bp.get("/dead-letter")
@jwt_required()
def dead_letter():
    limit = request.args.get("limit", 20, type=int)
    return jsonify(jobs=get_dead_letter_jobs(limit))


@bp.get("/<job_id>")
@jwt_required()
def job_status(job_id):
    status = get_job_status(job_id)
    if not status:
        return jsonify(error="not found"), 404
    return jsonify(status)


@bp.post("/<job_id>/retry")
@jwt_required()
def retry_job(job_id):
    if retry_dead_letter_job(job_id):
        return jsonify(message="job re-queued")
    return jsonify(error="job not found or not in dead letter state"), 404
