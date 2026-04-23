"""Admin routes for background task monitoring and management."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import Task, TaskStatus, User, Role
from ..services.taskqueue import queue_stats, retry_dead_task, purge_dead_tasks

bp = Blueprint("tasks", __name__)


def _is_admin(uid: int) -> bool:
    user = db.session.get(User, uid)
    return user is not None and user.role == Role.ADMIN.value


@bp.get("")
@bp.get("/")
@jwt_required()
def list_tasks():
    uid = int(get_jwt_identity())
    if not _is_admin(uid):
        return jsonify(error="forbidden"), 403

    status_filter = request.args.get("status")
    task_type = request.args.get("task_type")
    limit = min(int(request.args.get("limit", 50)), 200)
    offset = int(request.args.get("offset", 0))

    q = Task.query
    if status_filter:
        try:
            status_filter = TaskStatus(status_filter)
            q = q.filter_by(status=status_filter)
        except ValueError:
            return jsonify(error=f"invalid status. Use: {[s.value for s in TaskStatus]}"), 400
    if task_type:
        q = q.filter_by(task_type=task_type)

    tasks = q.order_by(Task.created_at.desc()).offset(offset).limit(limit).all()
    return jsonify([t.to_dict() for t in tasks])


@bp.get("/stats")
@jwt_required()
def get_stats():
    uid = int(get_jwt_identity())
    if not _is_admin(uid):
        return jsonify(error="forbidden"), 403
    return jsonify(queue_stats())


@bp.get("/<int:task_id>")
@jwt_required()
def get_task(task_id: int):
    uid = int(get_jwt_identity())
    if not _is_admin(uid):
        return jsonify(error="forbidden"), 403
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify(error="not found"), 404
    return jsonify(task.to_dict())


@bp.post("/<int:task_id>/retry")
@jwt_required()
def retry_task(task_id: int):
    uid = int(get_jwt_identity())
    if not _is_admin(uid):
        return jsonify(error="forbidden"), 403
    ok = retry_dead_task(task_id)
    if not ok:
        return jsonify(error="task not found or not dead"), 404
    return jsonify(status="retried"), 200


@bp.post("/purge")
@jwt_required()
def purge():
    uid = int(get_jwt_identity())
    if not _is_admin(uid):
        return jsonify(error="forbidden"), 403
    hours = int(request.args.get("older_than_hours", 168))
    count = purge_dead_tasks(hours)
    return jsonify(purged=count), 200
