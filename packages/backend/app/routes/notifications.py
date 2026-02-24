"""API routes for notification priority & grouping (#122)."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.notifications import (
    Notification, create_notification, get_notifications,
    get_grouped_notifications, mark_read, mark_all_read,
)

bp = Blueprint("notifications", __name__)
logger = logging.getLogger("finmind.notifications")


def _serialize(n):
    return {
        "id": n.id,
        "title": n.title,
        "message": n.message,
        "priority": n.priority,
        "group": n.group,
        "read": n.read,
        "created_at": n.created_at.isoformat(),
    }


@bp.get("")
@jwt_required()
def list_notifications():
    uid = int(get_jwt_identity())
    unread = request.args.get("unread", "").lower() == "true"
    group = request.args.get("group")
    items = get_notifications(uid, unread_only=unread, group=group)
    return jsonify([_serialize(n) for n in items])


@bp.get("/grouped")
@jwt_required()
def grouped():
    uid = int(get_jwt_identity())
    unread = request.args.get("unread", "").lower() == "true"
    groups = get_grouped_notifications(uid, unread_only=unread)
    result = {}
    for g, items in groups.items():
        result[g] = [_serialize(n) for n in items]
    return jsonify(result)


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    title = (data.get("title") or "").strip()
    message = (data.get("message") or "").strip()
    if not title or not message:
        return jsonify(error="title and message required"), 400
    priority = data.get("priority", "MEDIUM").upper()
    group = data.get("group", "SYSTEM").upper()
    n = create_notification(uid, title, message, priority=priority, group=group)
    return jsonify(_serialize(n)), 201


@bp.post("/read")
@jwt_required()
def mark_as_read():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    ids = data.get("ids", [])
    if not ids:
        return jsonify(error="ids required"), 400
    count = mark_read(uid, ids)
    return jsonify(marked=count)


@bp.post("/read-all")
@jwt_required()
def mark_all():
    uid = int(get_jwt_identity())
    count = mark_all_read(uid)
    return jsonify(marked=count)
