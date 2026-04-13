"""Event-driven financial activity system."""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog
import logging
bp = Blueprint("events", __name__)

@bp.post("/emit")
@jwt_required()
def emit_event():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    event_type = (data.get("event_type") or "").strip()
    if not event_type:
        return jsonify(error="event_type required"), 400
    entry = AuditLog(user_id=uid, action=f"event:{event_type}")
    db.session.add(entry)
    db.session.commit()
    return jsonify(id=entry.id, event_type=event_type, created_at=entry.created_at.isoformat()), 201

@bp.get("/stream")
@jwt_required()
def get_events():
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 50)), 200)
    event_type = request.args.get("type")
    q = db.session.query(AuditLog).filter_by(user_id=uid)
    if event_type:
        q = q.filter(AuditLog.action == f"event:{event_type}")
    events = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return jsonify([{"id": e.id, "event_type": e.action.replace("event:", ""), "created_at": e.created_at.isoformat()} for e in events])

@bp.get("/types")
@jwt_required()
def event_types():
    uid = int(get_jwt_identity())
    types = db.session.query(AuditLog.action).filter_by(user_id=uid).filter(AuditLog.action.like("event:%")).distinct().all()
    return jsonify(types=[t[0].replace("event:", "") for t in types])
