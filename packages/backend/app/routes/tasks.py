"""
API routes for task monitoring and management.
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..extensions import redis_client
from ..tasks.monitoring import (
    get_task_statistics,
    get_dead_letter_items,
    retry_dead_letter_item,
)

bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")


@bp.get("/stats")
@jwt_required()
def get_stats():
    """Get task execution statistics."""
    stats = get_task_statistics()
    return jsonify(stats), 200


@bp.get("/dead-letter")
@jwt_required()
def list_dead_letter():
    """List all dead letter queue items."""
    items = get_dead_letter_items()
    return jsonify({"items": items, "count": len(items)}), 200


@bp.post("/dead-letter/retry")
@jwt_required()
def retry_dead_letter():
    """Retry a dead letter item by key."""
    data = request.get_json()
    key = data.get("key")
    
    if not key:
        return jsonify({"error": "key is required"}), 400
    
    success = retry_dead_letter_item(key)
    if success:
        return jsonify({"message": "Retry initiated", "key": key}), 200
    else:
        return jsonify({"error": "Failed to retry item"}), 400


@bp.get("/active")
@jwt_required()
def list_active_tasks():
    """List currently active tasks."""
    keys = redis_client.keys("task:active:*")
    tasks = []
    
    for key in keys:
        data = redis_client.get(key)
        if data:
            import json
            try:
                task_data = json.loads(data)
                task_data["task_id"] = key.decode().split(":")[-1] if isinstance(key, bytes) else key.split(":")[-1]
                tasks.append(task_data)
            except json.JSONDecodeError:
                pass
    
    return jsonify({"tasks": tasks, "count": len(tasks)}), 200
