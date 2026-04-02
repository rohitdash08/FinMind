import time
import uuid
import threading
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

bp = Blueprint("jobs", __name__)
logger = logging.getLogger("finmind.jobs")

VALID_JOB_TYPES = {"export_data", "generate_report", "sync_transactions"}
MAX_RETRIES = 3

# In-memory job store: {job_id: {...}}
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _run_job(job_id: str) -> None:
    """Simulate async job execution with retry logic."""
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"

    # Simulate work that always fails for demo (replace with real logic)
    import random

    success = random.random() > 0.5  # noqa: S311

    with _lock:
        job = _jobs[job_id]
        if success:
            job["status"] = "complete"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            logger.info("Job %s completed", job_id)
        else:
            job["retry_count"] += 1
            error_msg = f"Simulated failure at {datetime.now(timezone.utc).isoformat()}"
            job["failures"].append(
                {"timestamp": datetime.now(timezone.utc).isoformat(), "error": error_msg}
            )
            if job["retry_count"] >= MAX_RETRIES:
                job["status"] = "failed"
                logger.warning("Job %s failed after %d retries", job_id, MAX_RETRIES)
            else:
                backoff = 2 ** job["retry_count"]
                job["status"] = "pending"
                job["next_retry_at"] = datetime.fromtimestamp(
                    time.time() + backoff, tz=timezone.utc
                ).isoformat()
                logger.info(
                    "Job %s retry %d in %ds", job_id, job["retry_count"], backoff
                )
                threading.Timer(backoff, _run_job, args=[job_id]).start()


@bp.post("")
@jwt_required()
def create_job():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    job_type = data.get("job_type")
    if job_type not in VALID_JOB_TYPES:
        return jsonify(error=f"Invalid job_type. Must be one of: {', '.join(sorted(VALID_JOB_TYPES))}"), 400

    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    job = {
        "id": job_id,
        "user_id": uid,
        "job_type": job_type,
        "status": "pending",
        "retry_count": 0,
        "next_retry_at": None,
        "created_at": now,
        "completed_at": None,
        "failures": [],
    }
    with _lock:
        _jobs[job_id] = job

    logger.info("Created job %s type=%s user=%s", job_id, job_type, uid)
    threading.Thread(target=_run_job, args=[job_id], daemon=True).start()
    return jsonify(job), 201


@bp.get("")
@jwt_required()
def list_jobs():
    uid = int(get_jwt_identity())
    with _lock:
        user_jobs = [j for j in _jobs.values() if j["user_id"] == uid]
    user_jobs.sort(key=lambda j: j["created_at"], reverse=True)
    return jsonify(user_jobs)


@bp.get("/<job_id>")
@jwt_required()
def get_job(job_id: str):
    uid = int(get_jwt_identity())
    with _lock:
        job = _jobs.get(job_id)
    if not job or job["user_id"] != uid:
        return jsonify(error="not found"), 404
    return jsonify(job)
