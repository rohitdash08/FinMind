"""Notification priority and grouping system."""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog
bp = Blueprint("notifications", __name__)

PRIORITIES = {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 5}

@bp.post("")
@jwt_required()
def create_notification():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    priority = (data.get("priority") or "medium").strip().lower()
    group = (data.get("group") or "general").strip()
    if not message: return jsonify(error="message required"), 400
    if priority not in PRIORITIES: return jsonify(error="invalid priority"), 400
    entry = AuditLog(user_id=uid, action=f"notif:{priority}:{group}:{message}")
    db.session.add(entry)
    db.session.commit()
    return jsonify(id=entry.id, message=message, priority=priority, group=group, created_at=entry.created_at.isoformat()), 201

@bp.get("")
@jwt_required()
def list_notifications():
    uid = int(get_jwt_identity())
    priority = request.args.get("priority")
    group = request.args.get("group")
    q = db.session.query(AuditLog).filter_by(user_id=uid).filter(AuditLog.action.like("notif:%"))
    if priority: q = q.filter(AuditLog.action.like(f"notif:{priority}:%"))
    if group: q = q.filter(AuditLog.action.like(f"notif:%:{group}:%"))
    entries = q.order_by(AuditLog.created_at.desc()).limit(50).all()
    results = []
    for e in entries:
        parts = e.action.split(":", 3)
        if len(parts) >= 4:
            results.append({"id": e.id, "priority": parts[1], "group": parts[2], "message": parts[3], "created_at": e.created_at.isoformat()})
    return jsonify(results)

@bp.get("/grouped")
@jwt_required()
def grouped():
    uid = int(get_jwt_identity())
    entries = db.session.query(AuditLog).filter_by(user_id=uid).filter(AuditLog.action.like("notif:%")).order_by(AuditLog.created_at.desc()).limit(100).all()
    groups = {}
    for e in entries:
        parts = e.action.split(":", 3)
        if len(parts) >= 4:
            g = parts[2]
            groups.setdefault(g, []).append({"id": e.id, "priority": parts[1], "message": parts[3], "created_at": e.created_at.isoformat()})
    return jsonify(groups=groups, group_count=len(groups))
