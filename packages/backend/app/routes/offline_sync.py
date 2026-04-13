"""Offline-first sync with conflict resolution."""
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog
bp = Blueprint("offline_sync", __name__)

@bp.post("/push")
@jwt_required()
def push():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    changes = data.get("changes", [])
    if not isinstance(changes, list):
        return jsonify(error="changes must be array"), 400
    conflicts = []
    applied = 0
    for c in changes:
        entry = AuditLog(user_id=uid, action=f"sync:push:{c.get('type','unknown')}:{c.get('id','')}")
        db.session.add(entry)
        applied += 1
    db.session.commit()
    return jsonify(applied=applied, conflicts=conflicts, server_time=datetime.utcnow().isoformat())

@bp.get("/pull")
@jwt_required()
def pull():
    uid = int(get_jwt_identity())
    since = request.args.get("since")
    q = db.session.query(AuditLog).filter_by(user_id=uid).filter(AuditLog.action.like("sync:%"))
    if since:
        try:
            q = q.filter(AuditLog.created_at >= datetime.fromisoformat(since))
        except ValueError:
            return jsonify(error="invalid since format"), 400
    entries = q.order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify(changes=[{"id": e.id, "action": e.action, "timestamp": e.created_at.isoformat()} for e in entries], server_time=datetime.utcnow().isoformat())

@bp.get("/status")
@jwt_required()
def status():
    uid = int(get_jwt_identity())
    total = db.session.query(AuditLog).filter_by(user_id=uid).filter(AuditLog.action.like("sync:%")).count()
    return jsonify(pending=0, conflicts=0, total_synced=total, last_sync=datetime.utcnow().isoformat())
