import json
import logging
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import AuditLog

bp = Blueprint("encryption", __name__)
logger = logging.getLogger("finmind.encryption")


@bp.post("/keys")
@jwt_required()
def store_key():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    key_id = (data.get("key_id") or "").strip()
    algorithm = (data.get("algorithm") or "").strip()
    if not key_id or not algorithm:
        return jsonify(error="key_id and algorithm required"), 400

    meta = {
        "key_id": key_id,
        "algorithm": algorithm,
        "created_at": datetime.utcnow().isoformat(),
    }
    log = AuditLog(user_id=uid, action=f"encryption_key:{json.dumps(meta)}")
    db.session.add(log)
    db.session.commit()
    logger.info("Stored key metadata user=%s key_id=%s", uid, key_id)
    return jsonify(meta), 201


@bp.get("/keys")
@jwt_required()
def list_keys():
    uid = int(get_jwt_identity())
    rows = (
        db.session.query(AuditLog)
        .filter(AuditLog.user_id == uid, AuditLog.action.like("encryption_key:%"))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    keys = []
    for r in rows:
        try:
            meta = json.loads(r.action.split(":", 1)[1])
            keys.append(meta)
        except (json.JSONDecodeError, IndexError):
            continue
    return jsonify(keys)


@bp.post("/verify")
@jwt_required()
def verify_hash():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    data_hash = (data.get("data_hash") or "").strip()
    expected_hash = (data.get("expected_hash") or "").strip()
    if not data_hash or not expected_hash:
        return jsonify(error="data_hash and expected_hash required"), 400

    valid = data_hash == expected_hash
    logger.info("Hash verify user=%s valid=%s", uid, valid)
    return jsonify({"valid": valid})
