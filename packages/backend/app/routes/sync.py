"""Offline-first sync API."""

from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.offline_sync import (
    queue_change, get_pending, sync_batch, get_changes_since,
    get_conflicts, resolve_conflict, get_sync_state,
)

bp = Blueprint("sync", __name__)


@bp.get("/state")
@jwt_required()
def state():
    uid = int(get_jwt_identity())
    return jsonify(get_sync_state(uid))


@bp.get("/pending")
@jwt_required()
def pending():
    uid = int(get_jwt_identity())
    return jsonify(get_pending(uid))


@bp.post("/push")
@jwt_required()
def push():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    changes = data.get("changes", [])
    if not changes:
        return jsonify({"error": "changes array required"}), 400
    return jsonify(sync_batch(uid, changes))


@bp.get("/pull")
@jwt_required()
def pull():
    uid = int(get_jwt_identity())
    since = request.args.get("since")
    since_dt = datetime.fromisoformat(since) if since else None
    return jsonify(get_changes_since(uid, since_dt))


@bp.get("/conflicts")
@jwt_required()
def conflicts():
    uid = int(get_jwt_identity())
    return jsonify(get_conflicts(uid))


@bp.post("/conflicts/<int:queue_id>/resolve")
@jwt_required()
def resolve(queue_id):
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        return jsonify(resolve_conflict(uid, queue_id, data.get("resolution", "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
