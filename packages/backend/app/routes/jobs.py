from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import BackgroundJob
from ..services.background_jobs import enqueue_job, run_due_jobs, serialize_job

bp = Blueprint("jobs", __name__)


@bp.get("")
@jwt_required()
def list_jobs():
    uid = int(get_jwt_identity())
    status = request.args.get("status")
    query = db.session.query(BackgroundJob).filter_by(user_id=uid)
    if status:
        query = query.filter(BackgroundJob.status == status.upper())
    jobs = query.order_by(BackgroundJob.created_at.desc()).limit(100).all()
    return jsonify([serialize_job(job) for job in jobs])


@bp.post("")
@jwt_required()
def create_job():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify(error="name is required"), 400
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        return jsonify(error="payload must be an object"), 400
    run_at = _parse_datetime(data.get("run_at"))
    max_attempts = int(data.get("max_attempts") or 3)
    job = enqueue_job(
        name,
        payload,
        user_id=uid,
        run_at=run_at,
        max_attempts=max_attempts,
    )
    return jsonify(serialize_job(job)), 201


@bp.get("/<int:job_id>")
@jwt_required()
def get_job(job_id: int):
    uid = int(get_jwt_identity())
    job = db.session.get(BackgroundJob, job_id)
    if not job or job.user_id != uid:
        return jsonify(error="not found"), 404
    return jsonify(serialize_job(job))


@bp.post("/run")
@jwt_required()
def run_jobs():
    data = request.get_json(silent=True) or {}
    limit = min(max(int(data.get("limit") or 25), 1), 100)
    stats = run_due_jobs(limit=limit)
    return jsonify(stats), 200


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
