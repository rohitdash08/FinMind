"""API routes for background job monitoring and management.

Provides endpoints for operators and admins to:
- View job status, history, and health
- Inspect dead-lettered jobs
- Reset failed jobs for retry
"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Role

bp = Blueprint("jobs", __name__)


def _require_admin():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user or user.role != Role.ADMIN.value:
        return None, (jsonify(error="admin access required"), 403)
    return user, None


@bp.get("/status")
@jwt_required()
def job_status():
    """Get status of all managed background jobs."""
    user, err = _require_admin()
    if err:
        return err

    from ..services.job_manager import job_manager
    status = job_manager.get_status()
    return jsonify(jobs=status), 200


@bp.get("/dead-letters")
@jwt_required()
def dead_letters():
    """List jobs that exhausted all retries."""
    user, err = _require_admin()
    if err:
        return err

    from ..services.job_manager import job_manager
    dead = job_manager.get_dead_letters()
    return jsonify(dead_letters=dead), 200


@bp.post("/<job_id>/reset")
@jwt_required()
def reset_job(job_id: str):
    """Reset a dead-lettered job so it retries on next trigger."""
    user, err = _require_admin()
    if err:
        return err

    from ..services.job_manager import job_manager
    if job_manager.reset_job(job_id):
        return jsonify(message=f"Job {job_id} reset successfully"), 200
    return jsonify(error=f"Job {job_id} not found"), 404


@bp.get("/health")
def job_health():
    """Unauthenticated health check for monitoring systems.

    Returns a summary without sensitive details.
    """
    from ..services.job_manager import job_manager
    status = job_manager.get_status()
    summary = {}
    all_healthy = True
    for jid, info in status.items():
        healthy = info["status"] not in ("failed", "missed")
        summary[jid] = {
            "healthy": healthy,
            "status": info["status"],
            "total_runs": info["total_runs"],
            "total_failures": info["total_failures"],
        }
        if not healthy:
            all_healthy = False

    return jsonify(
        healthy=all_healthy,
        jobs=summary,
    ), 200 if all_healthy else 503
