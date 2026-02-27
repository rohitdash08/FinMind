"""Resilient background job retry & monitoring API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.job_retry import (
    create_job, start_job, complete_job, fail_job, retry_due_jobs,
    get_job, list_jobs, get_dead_letter_queue, requeue_dead,
    get_logs, get_stats, JOB_TYPES,
)

bp = Blueprint("jobs_retry", __name__)


@bp.get("/types")
@jwt_required()
def types():
    return jsonify(JOB_TYPES)


@bp.post("/")
@jwt_required()
def create():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("job_type"):
        return jsonify({"error": "name and job_type required"}), 400
    try:
        return jsonify(create_job(data["name"], data["job_type"],
                                  data.get("payload"), data.get("max_retries", 3),
                                  data.get("priority", 0))), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/")
@jwt_required()
def list_all():
    status = request.args.get("status")
    job_type = request.args.get("type")
    limit = int(request.args.get("limit", 50))
    return jsonify(list_jobs(status, job_type, limit))


@bp.get("/stats")
@jwt_required()
def stats():
    return jsonify(get_stats())


@bp.get("/dead-letter")
@jwt_required()
def dlq():
    return jsonify(get_dead_letter_queue())


@bp.get("/<int:job_id>")
@jwt_required()
def detail(job_id):
    j = get_job(job_id)
    if not j:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(j)


@bp.post("/<int:job_id>/start")
@jwt_required()
def start(job_id):
    try:
        return jsonify(start_job(job_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/<int:job_id>/complete")
@jwt_required()
def complete(job_id):
    data = request.get_json() or {}
    try:
        return jsonify(complete_job(job_id, data.get("message", ""), data.get("duration_ms", 0)))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/<int:job_id>/fail")
@jwt_required()
def fail(job_id):
    data = request.get_json() or {}
    try:
        return jsonify(fail_job(job_id, data.get("error", "Unknown"), data.get("duration_ms", 0)))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.post("/<int:job_id>/requeue")
@jwt_required()
def requeue(job_id):
    try:
        return jsonify(requeue_dead(job_id))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/<int:job_id>/logs")
@jwt_required()
def logs(job_id):
    return jsonify(get_logs(job_id))


@bp.post("/retry-due")
@jwt_required()
def retry():
    return jsonify(retry_due_jobs())
