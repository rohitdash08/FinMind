"""Job monitoring route.

Endpoints
---------
GET /jobs/status   — returns current execution state for all registered jobs
                     (JWT required)
POST /jobs/trigger/<job_id>  — manually trigger a scheduled job immediately
                               (JWT required)
"""
from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required
import logging

from ..services.job_retry import job_monitor

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs.routes")


@bp.get("/status")
@jwt_required()
def job_status():
    """Return execution health of all registered background jobs."""
    records = job_monitor.all_records()
    return jsonify({
        "job_count": len(records),
        "jobs": [r.to_dict() for r in records],
    })


@bp.post("/trigger/<job_id>")
@jwt_required()
def trigger_job(job_id: str):
    """Manually fire a scheduled job by its APScheduler id."""
    scheduler = current_app.extensions.get("job_scheduler")
    if not scheduler:
        return jsonify(error="scheduler not running"), 503

    job = scheduler.get_job(job_id)
    if not job:
        return jsonify(error=f"job '{job_id}' not found"), 404

    job.modify(next_run_time=__import__("datetime").datetime.utcnow())
    logger.info("Manually triggered job id=%s", job_id)
    return jsonify(message=f"job '{job_id}' triggered"), 200
