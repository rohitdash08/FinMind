import logging
from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import redis_client
from ..services.gdpr import (
    export_user_data,
    _enqueue_export_job,
    request_deletion,
    cancel_deletion,
    confirm_deletion,
    get_deletion_status,
)
from ..models import User
import json
import os
import tempfile
import zipfile

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


@bp.get("/export")
@jwt_required()
def export_data():
    """Export all user data as JSON. For large datasets, triggers async job."""
    uid = int(get_jwt_identity())
    user = User.query.get(uid)
    if not user:
        return jsonify(error="user not found"), 404

    # Check if there's an existing pending job
    status_key = f"gdpr:status:{uid}"
    existing = redis_client.hgetall(status_key)
    if existing and existing.get("status") in ("queued", "processing"):
        return (
            jsonify(
                status=existing.get("status"),
                job_id=existing.get("job_id"),
                message="Export already in progress",
            ),
            202,
        )
    if existing and existing.get("status") == "completed":
        # Return existing result if still available
        download_key = existing.get("download_key")
        if download_key and redis_client.exists(download_key):
            data = json.loads(redis_client.get(download_key))
            return jsonify(data), 200

    # For moderate data size, generate synchronously; else async
    # We'll start async job to be safe
    job_id = _enqueue_export_job(uid)
    return (
        jsonify(
            status="queued",
            job_id=job_id,
            message="Export job queued. Poll /api/gdpr/status for completion.",
        ),
        202,
    )


@bp.get("/status")
@jwt_required()
def get_status():
    """Get GDPR request status (export and deletion)."""
    uid = int(get_jwt_identity())
    deletion_status = get_deletion_status(uid)
    export_status_key = f"gdpr:status:{uid}"
    export_data = redis_client.hgetall(export_status_key)

    result = {"deletion": deletion_status}
    if export_data:
        result["export"] = dict(export_data)
    else:
        result["export"] = {"status": "none"}

    return jsonify(result)


@bp.post("/delete")
@jwt_required()
def request_delete():
    """Request account deletion with 30-day grace period."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("password")
    if not password:
        return jsonify(error="password required"), 400

    try:
        result = request_deletion(uid, password)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.post("/delete/cancel")
@jwt_required()
def cancel_delete():
    """Cancel deletion request during grace period."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    password = data.get("password")
    if not password:
        return jsonify(error="password required"), 400

    try:
        result = cancel_deletion(uid, password)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify(error=str(e)), 400


@bp.post("/delete/confirm")
@jwt_required()
def confirm_delete():
    """Confirm and execute immediate deletion (bypass grace period)."""
    uid = int(get_jwt_identity())
    try:
        result = confirm_deletion(uid)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify(error=str(e)), 400
