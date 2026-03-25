"""
API routes for background job management.

Provides endpoints for:
- Viewing job status
- Monitoring job metrics
- Managing dead letter queue
- Manual retry operations
"""

from flask import Blueprint, jsonify, request, current_app
from ..services.background_jobs import (
    BackgroundJobService,
    BackgroundJob,
    JobStatus,
    JobType,
    job_metrics,
)

bp = Blueprint("background_jobs", __name__, url_prefix="/api/jobs")


@bp.get("/metrics")
def get_metrics():
    """Get aggregated job metrics for monitoring."""
    return jsonify(job_metrics.get_stats())


@bp.get("/<int:job_id>")
def get_job_status(job_id: int):
    """Get status of a specific job."""
    status = BackgroundJobService.get_job_status(job_id)
    if not status:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(status)


@bp.get("/pending")
def get_pending_jobs():
    """Get list of pending and retrying jobs."""
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    
    jobs = BackgroundJob.query.filter(
        BackgroundJob.status.in_([
            JobStatus.PENDING.value,
            JobStatus.RETRYING.value
        ])
    ).order_by(
        BackgroundJob.priority.desc(),
        BackgroundJob.created_at.asc()
    ).paginate(page=page, per_page=per_page)
    
    return jsonify({
        "jobs": [
            BackgroundJobService.get_job_status(job.id)
            for job in jobs.items
        ],
        "total": jobs.total,
        "page": page,
        "per_page": per_page,
        "pages": jobs.pages,
    })


@bp.get("/dead-letter")
def get_dead_letter_queue():
    """Get jobs in the dead letter queue."""
    limit = request.args.get("limit", 50, type=int)
    jobs = BackgroundJobService.get_dead_letter_jobs(limit=limit)
    return jsonify({
        "jobs": jobs,
        "count": len(jobs),
    })


@bp.post("/<int:job_id>/retry")
def retry_job(job_id: int):
    """Manually retry a failed job from the dead letter queue."""
    success = BackgroundJobService.retry_dead_letter_job(job_id)
    if not success:
        return jsonify({
            "error": "Job not found or not in dead letter queue"
        }), 404
    
    return jsonify({
        "success": True,
        "message": f"Job {job_id} queued for retry"
    })


@bp.post("/process")
def process_jobs():
    """
    Manually trigger job processing.
    
    This endpoint is useful for testing or manual intervention.
    In production, jobs should be processed by a background worker.
    """
    limit = request.args.get("limit", 10, type=int)
    stats = BackgroundJobService.process_pending_jobs(limit=limit)
    
    return jsonify({
        "success": True,
        "stats": stats
    })


@bp.post("/cleanup")
def cleanup_jobs():
    """Remove old completed jobs."""
    days = request.args.get("days", 30, type=int)
    deleted = BackgroundJobService.cleanup_old_jobs(days=days)
    
    return jsonify({
        "success": True,
        "deleted_count": deleted
    })


@bp.get("/health")
def jobs_health():
    """Health check endpoint for background job system."""
    from ..extensions import db
    from sqlalchemy import func
    
    # Count jobs by status
    status_counts = dict(
        db.session.query(
            BackgroundJob.status,
            func.count(BackgroundJob.id)
        ).group_by(BackgroundJob.status).all()
    )
    
    # Check for stuck jobs (running for too long)
    from datetime import datetime, timedelta
    stuck_threshold = datetime.utcnow() - timedelta(hours=1)
    stuck_count = BackgroundJob.query.filter(
        BackgroundJob.status == JobStatus.RUNNING.value,
        BackgroundJob.started_at < stuck_threshold
    ).count()
    
    # Determine health status
    is_healthy = stuck_count == 0
    
    return jsonify({
        "status": "healthy" if is_healthy else "degraded",
        "status_counts": status_counts,
        "stuck_jobs": stuck_count,
        "metrics": job_metrics.get_stats(),
    })