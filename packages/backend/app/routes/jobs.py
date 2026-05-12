from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import JobExecution
from ..services.jobs import get_job_stats, execute_job, process_pending_jobs
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")


@bp.get("/stats")
@jwt_required()
def job_stats():
    uid = int(get_jwt_identity())
    stats = get_job_stats(user_id=uid)
    logger.info("Job stats requested user=%s", uid)
    return jsonify(stats)


@bp.get("/recent")
@jwt_required()
def recent_jobs():
    uid = int(get_jwt_identity())
    status_filter = request.args.get("status")
    job_type_filter = request.args.get("job_type")
    limit = min(int(request.args.get("limit", 50)), 100)

    query = db.session.query(JobExecution).filter_by(user_id=uid)
    if status_filter:
        query = query.filter_by(status=status_filter)
    if job_type_filter:
        query = query.filter_by(job_type=job_type_filter)

    items = query.order_by(JobExecution.created_at.desc()).limit(limit).all()
    logger.info("Recent jobs user=%s count=%s", uid, len(items))
    return jsonify(
        [
            {
                "id": j.id,
                "job_type": j.job_type,
                "status": j.status,
                "attempts": j.attempts,
                "max_attempts": j.max_attempts,
                "last_error": j.last_error,
                "next_retry_at": j.next_retry_at.isoformat() if j.next_retry_at else None,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
            }
            for j in items
        ]
    )


@bp.post("/retry/<int:job_id>")
@jwt_required()
def retry_job(job_id: int):
    uid = int(get_jwt_identity())
    job = db.session.get(JobExecution, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="not found"), 404
    if job.status != "failed":
        return jsonify(error="only failed jobs can be retried"), 400

    job.status = "pending"
    job.attempts = 0
    job.last_error = None
    job.next_retry_at = None
    db.session.commit()

    result = execute_job(job.id)
    logger.info("Manual retry job id=%s user=%s status=%s", job_id, uid, result.status)
    return jsonify(
        {
            "id": result.id,
            "status": result.status,
            "attempts": result.attempts,
            "last_error": result.last_error,
        }
    )


@bp.post("/process")
@jwt_required()
def process_jobs():
    uid = int(get_jwt_identity())
    results = process_pending_jobs()
    logger.info("Process jobs triggered user=%s processed=%s", uid, len(results))
    return jsonify(processed=len(results))
