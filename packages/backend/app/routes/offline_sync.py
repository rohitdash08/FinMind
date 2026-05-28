"""Offline-First Sync API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.offline_sync import SyncService

bp = Blueprint("offline_sync", __name__)

# Per-user sync services (in production, use Redis/DB)
_sync_services = {}


def _get_sync_service(user_id: str) -> SyncService:
    if user_id not in _sync_services:
        _sync_services[user_id] = SyncService()
    return _sync_services[user_id]


@bp.post("/push")
@jwt_required()
def push_operations():
    """Push offline operations to server."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    operations = data.get("operations", [])
    device_id = data.get("device_id", "unknown")

    sync = _get_sync_service(user_id)
    result = sync.apply_operations(operations, device_id)
    return jsonify(result)


@bp.post("/pull")
@jwt_required()
def pull_deltas():
    """Pull changes since last sync."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    since_version = int(data.get("since_version", 0))

    sync = _get_sync_service(user_id)
    result = sync.get_deltas(since_version)
    return jsonify(result)


@bp.post("/full-sync")
@jwt_required()
def full_sync():
    """Full sync - get complete server state."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    sync = _get_sync_service(user_id)
    server_state = sync.get_server_state()

    # If client has operations, apply them first
    if data.get("operations"):
        result = sync.apply_operations(data["operations"], data.get("device_id", ""))
        return jsonify({"sync_result": result, "server_state": server_state})

    return jsonify(server_state)
