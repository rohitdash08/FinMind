"""Background job management endpoints for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services import jobs as job_service

bp = Blueprint("jobs", __name__)


@bp.get("/stats")
@jwt_required()
def queue_stats():
    """Get statistics for a specific job queue."""
    job_type = (request.args.get("type") or "").strip()
    if not job_type:
        return jsonify(error="type parameter required"), 400
    stats = job_service.get_queue_stats(job_type)
    return jsonify(stats)


@bp.get("/dead-letters")
@jwt_required()
def list_dead_letters():
    """List dead-lettered jobs for a type."""
    job_type = (request.args.get("type") or "").strip()
    if not job_type:
        return jsonify(error="type parameter required"), 400
    try:
        limit = min(100, max(1, int(request.args.get("limit", "50"))))
    except ValueError:
        limit = 50
    items = job_service.get_dead_letters(job_type, limit=limit)
    return jsonify([j.to_dict() for j in items])


@bp.post("/dead-letters/<job_id>/retry")
@jwt_required()
def retry_dead_letter(job_id: str):
    """Re-queue a dead-lettered job for retry."""
    data = request.get_json() or {}
    job_type = data.get("type") or ""
    if not job_type:
        return jsonify(error="type required in body"), 400
    job = job_service.retry_dead_letter(job_id, job_type)
    if not job:
        return jsonify(error="job not found in dead letters"), 404
    return jsonify(job.to_dict())


@bp.delete("/dead-letters")
@jwt_required()
def purge_dead_letters():
    """Purge all dead-lettered jobs for a type."""
    job_type = (request.args.get("type") or "").strip()
    if not job_type:
        return jsonify(error="type parameter required"), 400
    count = job_service.purge_dead_letters(job_type)
    return jsonify(purged=count)
