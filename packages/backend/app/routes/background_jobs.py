"""Routes for background job queue management (issue #71)."""
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.background_jobs import (
    enqueue_job,
    cancel_job,
    get_job_stats,
    get_user_jobs,
    get_registered_job_types,
    BackgroundJob,
    JobPriority,
    JobStatus,
)

bp = Blueprint("background_jobs", __name__)

VALID_PRIORITIES = {p.value for p in JobPriority}
VALID_STATUSES = {s.value for s in JobStatus}


@bp.route("/jobs", methods=["POST"])
@jwt_required()
def create_job():
    """Enqueue a new background job."""
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    job_type = data.get("job_type", "").strip()
    if not job_type:
        return jsonify({"error": "job_type is required"}), 400

    registered_types = get_registered_job_types()
    if registered_types and job_type not in registered_types:
        return jsonify({
            "error": f"Unknown job_type. Registered types: {registered_types}"
        }), 400

    priority = data.get("priority", JobPriority.NORMAL.value)
    if priority not in VALID_PRIORITIES:
        return jsonify({"error": f"priority must be one of: {list(VALID_PRIORITIES)}"}), 400

    max_retries = int(data.get("max_retries", 3))
    if not 0 <= max_retries <= 10:
        return jsonify({"error": "max_retries must be between 0 and 10"}), 400

    job = enqueue_job(
        job_type=job_type,
        payload=data.get("payload", {}),
        user_id=user_id,
        priority=priority,
        max_retries=max_retries,
    )
    return jsonify(job.to_dict()), 201


@bp.route("/jobs", methods=["GET"])
@jwt_required()
def list_jobs():
    """List background jobs for the current user."""
    user_id = int(get_jwt_identity())

    status = request.args.get("status")
    if status and status not in VALID_STATUSES:
        return jsonify({"error": f"status must be one of: {list(VALID_STATUSES)}"}), 400

    job_type = request.args.get("job_type")
    try:
        limit = min(int(request.args.get("limit", 20)), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    result = get_user_jobs(
        user_id=user_id,
        status=status,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )
    return jsonify(result), 200


@bp.route("/jobs/<int:job_id>", methods=["GET"])
@jwt_required()
def get_job(job_id: int):
    """Get a specific job by ID."""
    user_id = int(get_jwt_identity())
    job = BackgroundJob.query.filter_by(id=job_id, user_id=user_id).first()
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict()), 200


@bp.route("/jobs/<int:job_id>/cancel", methods=["POST"])
@jwt_required()
def cancel_job_route(job_id: int):
    """Cancel a pending or failed job."""
    user_id = int(get_jwt_identity())
    job = cancel_job(job_id=job_id, user_id=user_id)
    if not job:
        return jsonify({"error": "Job not found or cannot be cancelled"}), 404
    return jsonify(job.to_dict()), 200


@bp.route("/jobs/stats", methods=["GET"])
@jwt_required()
def job_stats():
    """Get job statistics for the current user."""
    user_id = int(get_jwt_identity())
    stats = get_job_stats(user_id=user_id)
    return jsonify(stats), 200


@bp.route("/jobs/types", methods=["GET"])
def list_job_types():
    """List registered job types (public endpoint)."""
    types = get_registered_job_types()
    return jsonify({"job_types": types, "count": len(types)}), 200