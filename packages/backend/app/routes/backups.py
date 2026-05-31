from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.backup import (
    create_backup,
    list_backups,
    get_backup,
    decrypt_backup,
    delete_backup,
)
import logging

bp = Blueprint("backups", __name__)
logger = logging.getLogger("finmind.backups")


@bp.post("")
@jwt_required()
def create():
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    password = body.get("password", "").strip()
    if len(password) < 8:
        return jsonify(error="password must be at least 8 characters"), 400
    export_type = body.get("export_type", "full").strip()
    result = create_backup(uid, password, export_type)
    logger.info("Backup created user=%s backup=%d", uid, result["id"])
    return jsonify(result), 201


@bp.get("")
@jwt_required()
def list_all():
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    result = list_backups(uid, limit)
    return jsonify({"backups": result})


@bp.get("/<int:backup_id>")
@jwt_required()
def get(backup_id: int):
    uid = int(get_jwt_identity())
    result = get_backup(uid, backup_id)
    if not result:
        return jsonify(error="backup not found"), 404
    return jsonify(result)


@bp.post("/<int:backup_id>/decrypt")
@jwt_required()
def decrypt(backup_id: int):
    uid = int(get_jwt_identity())
    body = request.get_json(silent=True) or {}
    password = body.get("password", "")
    data = decrypt_backup(uid, backup_id, password)
    if data is None:
        return jsonify(error="backup not found or invalid password"), 404
    return jsonify(data)


@bp.delete("/<int:backup_id>")
@jwt_required()
def delete(backup_id: int):
    uid = int(get_jwt_identity())
    result = delete_backup(uid, backup_id)
    if not result:
        return jsonify(error="backup not found"), 404
    return jsonify({"deleted": True})
