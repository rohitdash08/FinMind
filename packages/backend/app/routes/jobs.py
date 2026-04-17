from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.job_retry import get_job_status, get_failed_jobs, retry_dead_job

bp = Blueprint("jobs", __name__)

@bp.get("/status/<job_id>")
@jwt_required()
def job_status(job_id):
    status = get_job_status(job_id)
    if not status:
        return jsonify(error="Job not found"), 404
    return jsonify(status)

@bp.get("/dead")
@jwt_required()
def dead_letters():
    limit = request.args.get("limit", 50, type=int)
    return jsonify({"jobs": get_failed_jobs(limit)})

@bp.post("/retry/<job_id>")
@jwt_required()
def retry_job(job_id):
    if retry_dead_job(job_id):
        return jsonify(status="requeued", job_id=job_id)
    return jsonify(error="Job not found or not dead"), 404
