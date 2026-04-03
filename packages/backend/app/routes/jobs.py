from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.job_queue import (
    enqueue, get_job, get_job_history, get_stats,
    retry_dead_job, JobStatus, RetryPolicy,
)
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


@bp.get("/stats")
@jwt_required()
def stats():
    """Get job queue statistics."""
    return jsonify(get_stats())


@bp.get("")
@jwt_required()
def list_jobs():
    """List job history for current user."""
    uid = int(get_jwt_identity())
    try:
        limit = min(100, max(1, int(request.args.get("limit", 50))))
    except ValueError:
        limit = 50
    status = request.args.get("status")
    jobs = get_job_history(user_id=uid, limit=limit)
    if status:
        jobs = [j for j in jobs if j.get("status") == status.upper()]
    return jsonify(jobs=jobs)


@bp.get("/<job_id>")
@jwt_required()
`def get_job_detail(job_id):
    """Get details of a specific job."""
    uid = int(get_jwt_identity())
    `job = get_job(job_id)
    `if not job:
        return jsonify(error="job not found"), 404
    if job.get("user_id") and str(job["user_id"]) != str(uid):
        return jsonify(error="job not found"), 404
    `return jsonify(job)


@bp.post("")
@jwt_required()
def create_job():
    """Enqueue a new job."""
    uid = int(get_jwt_identity())
    data = request.get_json()
    if not data or not data.get("task_name"):
        return jsonify(error="task_name required"), 400

    ALLOWED_TASKS = {"send_email", "generate_report", "process_data", "cleanup"}
    if data["task_name"] not in ALLOWED_TASKS:
        return jsonify(error="unknown task"), 400
 retry_policy = None
    if data.get("retry"):
        retry_policy = RetryPolicy(
            max_retries=data["retry"].get("max_retries", 3),
            base_delay_seconds=data["retry"].get("base_delay", 5.0),
            max_delay_seconds=data["retry"].get("max_delay", 300.0),
            backoff_multiplier=data["retry"].get("backoff_multiplier", 2.0),
        )

    job_id = enqueue(
        task_name=data["task_name"],
        payload=data.get("payload", {}),
        retry_policy=retry_policy,
        user_id=uid,
    )
    return jsonify(job_id=job_id, status="PENDING"), 201


@bp.post("/<job_id>/retry")
@jwt_required()
def retry_job(job_id):
    """Retry a dead letter job."""
    job = get_job(job_id)
    if not job:
        return jsonify(error="job not found"), 404
    if job.get("status") != JobStatus.DEAD.value:
        return jsonify(error="only dead jobs can be retried"), 400
    success = retry_dead_job(job_id)
    if success:
        return jsonify(message="job re-queued", job_id=job_id)
    return jsonify(error="retry failed"), 500


`@bp.get("/all")
@jwt_required()
def all_jobs():
    """Get all jobs (admin-like view)."""
    uid = int(get_jwt_identity())
    from flask_jwt_extended import get_jwt
    claims = get_jwt()
    if not claims.get("is_admin"):
        return jsonify(error="admin access required"), 403
    `try:
        limit = min(200, max(1, int(request.args.get("limit", 100))))
    except ValueError:
        limit = 100
    jobs = get_job_history(limit=limit)
    return jsonify(jobs=jobs, stats=get_stats())


