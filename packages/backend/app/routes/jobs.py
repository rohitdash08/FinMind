from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BackgroundJob, JobHistory, JobStatus
from ..services.job_retry import (
    get_job_stats,
    get_dead_letter_jobs,
    get_job_history,
    job_to_dict,
)
import logging

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")

# Valid status values for filtering
_VALID_STATUSES = frozenset(s.value for s in JobStatus)


@bp.get("/stats")
@jwt_required()
def job_stats():
    stats = get_job_stats()
    return jsonify(stats)


@bp.get("")
@jwt_required()
def list_jobs():
    status = request.args.get("status")
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(100, max(1, int(request.args.get("page_size", "20"))))
    except ValueError:
        return jsonify(error="invalid pagination"), 400

    q = db.session.query(BackgroundJob)
    if status:
        normalised = status.upper().strip()
        if normalised not in _VALID_STATUSES:
            return jsonify(error=f"invalid status, must be one of: {sorted(_VALID_STATUSES)}"), 400
        q = q.filter(BackgroundJob.status == normalised)
    items = (
        q.order_by(BackgroundJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return jsonify([job_to_dict(j) for j in items])


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    data = job_to_dict(job)
    data["history"] = get_job_history(job_id)
    return jsonify(data)


@bp.get("/dead-letter")
@jwt_required()
def dead_letter_queue():
    try:
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        return jsonify(error="invalid limit"), 400
    jobs = get_dead_letter_jobs(limit=limit)
    return jsonify(jobs)


@bp.post("/<int:job_id>/retry")
@jwt_required()
def manual_retry(job_id: int):
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    if job.status not in (JobStatus.DEAD.value, JobStatus.FAILED.value):
        return jsonify(error="job is not in a failed state"), 400

    # Record the manual-retry event in history before resetting counters
    history_entry = JobHistory(
        job_id=job.id,
        attempt=job.attempts,
        status="MANUAL_RETRY",
        error=None,
    )
    db.session.add(history_entry)

    job.status = JobStatus.PENDING.value
    job.attempts = 0
    job.last_error = None
    job.completed_at = None
    job.next_retry_at = None
    db.session.commit()
    logger.info("Manual retry job id=%s", job.id)
    return jsonify(job_to_dict(job))


@bp.delete("/<int:job_id>")
@jwt_required()
def delete_job(job_id: int):
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404
    db.session.delete(job)
    db.session.commit()
    logger.info("Deleted job id=%s", job.id)
    return jsonify(message="deleted")
