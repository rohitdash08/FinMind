from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.jobs import enqueue_job, process_pending_jobs, get_job_stats, get_user_jobs, retry_dead_job
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.api")


@bp.get("")
@jwt_required()
def list_jobs():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", "50")
    try:
        limit = min(200, max(1, int(limit)))
    except ValueError:
        return jsonify(error="invalid limit"), 400
    jobs = get_user_jobs(uid, limit=limit)
    return jsonify(jobs)


@bp.post("")
@jwt_required()
def create_job():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    job_type = str(data.get("job_type") or "").strip()
    if not job_type:
        return jsonify(error="job_type required"), 400
    payload = data.get("payload")
    max_retries = data.get("max_retries", 3)
    try:
        max_retries = int(max_retries)
        if max_retries < 0:
            raise ValueError
    except ValueError:
        return jsonify(error="max_retries must be a non-negative integer"), 400
    job = enqueue_job(
        job_type=job_type,
        payload=payload,
        user_id=uid,
        max_retries=max_retries,
    )
    return jsonify(id=job.id, status=job.status, job_type=job.job_type), 201


@bp.post("/process")
@jwt_required()
def process_jobs():
    uid = int(get_jwt_identity())
    results = process_pending_jobs(limit=50)
    logger.info("Processed jobs user=%s results=%s", uid, results)
    return jsonify(results)


@bp.get("/stats")
@jwt_required()
def job_stats():
    stats = get_job_stats()
    return jsonify(stats)


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    uid = int(get_jwt_identity())
    job = retry_dead_job(job_id, uid=uid)
    if not job:
        return jsonify(error="job not found or not dead"), 404
    return jsonify(id=job.id, status=job.status)
