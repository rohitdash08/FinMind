from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import io
from ..services.backup import create_encrypted_backup, create_plaintext_backup

bp = Blueprint("backup", __name__)

@bp.post("/encrypted")
@jwt_required()
def encrypted_backup():
    uid = int(get_jwt_identity())
    d = request.get_json() or {}
    password = d.get("password")
    if not password or len(password) < 8:
        return jsonify(error="password required (min 8 chars)"), 400
    payload = create_encrypted_backup(uid, password)
    return send_file(io.BytesIO(payload), mimetype="application/octet-stream",
                     as_attachment=True, download_name=f"finmind-backup-{uid}.enc")

@bp.get("/plaintext")
@jwt_required()
def plaintext_backup():
    uid = int(get_jwt_identity())
    data = create_plaintext_backup(uid)
    return send_file(io.BytesIO(data), mimetype="application/zip",
                     as_attachment=True, download_name=f"finmind-backup-{uid}.zip")
