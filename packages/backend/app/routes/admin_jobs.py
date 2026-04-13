from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import BackgroundJob, JobExecutionLog, JobStatus, User, Role
from ..services.jobs import retry_failed_job
import logging

bp = Blueprint("admin_jobs", __name__)
logger = logging.getLogger("finmind.admin.jobs")


def _require_admin():
    """Return the user if they have ADMIN role, otherwise abort with 403."""
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != Role.ADMIN.value:
        return None
    return user


@bp.get("")
@jwt_required()
def list_jobs():
    user = _require_admin()
    if user is None:
        return jsonify(error="admin access required"), 403

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)
    status_filter = request.args.get("status")
    job_type_filter = request.args.get("job_type")

    query = db.session.query(BackgroundJob)
    if status_filter:
        query = query.filter(BackgroundJob.status == status_filter)
    if job_type_filter:
        query = query.filter(BackgroundJob.job_type == job_type_filter)

    query = query.order_by(BackgroundJob.created_at.desc())
    total = query.count()
    jobs = query.offset((page - 1) * per_page).limit(per_page).all()

    logger.info("Admin list jobs user=%s page=%s total=%s", user.id, page, total)
    return jsonify(
        jobs=[j.to_dict() for j in jobs],
        total=total,
        page=page,
        per_page=per_page,
    )


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    user = _require_admin()
    if user is None:
        return jsonify(error="admin access required"), 403

    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404

    logs = (
        db.session.query(JobExecutionLog)
        .filter_by(job_id=job_id)
        .order_by(JobExecutionLog.attempt)
        .all()
    )

    logger.info("Admin get job id=%s user=%s", job_id, user.id)
    return jsonify(
        job=job.to_dict(),
        execution_history=[log.to_dict() for log in logs],
    )


@bp.post("/<int:job_id>/retry")
@jwt_required()
def retry_job(job_id: int):
    user = _require_admin()
    if user is None:
        return jsonify(error="admin access required"), 403

    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify(error="not found"), 404

    if job.status != JobStatus.FAILED.value:
        return jsonify(error="only failed jobs can be retried"), 400

    result = retry_failed_job(job_id)
    logger.info("Admin retry job id=%s user=%s", job_id, user.id)
    return jsonify(job=result.to_dict())
