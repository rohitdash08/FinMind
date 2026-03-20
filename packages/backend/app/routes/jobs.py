"""Routes for background job monitoring."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services.job_runner import get_monitoring_stats, BackgroundJob, JobStatus

bp = Blueprint("jobs", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    hours = request.args.get("hours", 24, type=int)
    return jsonify(get_monitoring_stats(hours=hours))


@bp.get("/dead-letter")
@jwt_required()
def dead_letter_queue():
    jobs = (
        BackgroundJob.query.filter_by(status=JobStatus.DEAD_LETTERED.value)
        .order_by(BackgroundJob.completed_at.desc())
        .limit(50)
        .all()
    )
    return jsonify(
        jobs=[
            {
                "id": j.id,
                "name": j.name,
                "attempts": j.attempts,
                "last_error": (j.last_error or "")[:500],
                "created_at": j.created_at.isoformat(),
            }
            for j in jobs
        ]
    )


@bp.get("/history")
@jwt_required()
def history():
    limit = request.args.get("limit", 20, type=int)
    jobs = (
        BackgroundJob.query.order_by(BackgroundJob.created_at.desc())
        .limit(min(limit, 100))
        .all()
    )
    return jsonify(
        jobs=[
            {
                "id": j.id,
                "name": j.name,
                "status": j.status,
                "attempts": j.attempts,
                "duration_ms": j.duration_ms,
                "created_at": j.created_at.isoformat(),
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]
    )
