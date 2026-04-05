"""GDPR export & deletion API routes."""
from flask import Blueprint, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
import io
from ..services.gdpr import export_user_data, delete_user_account

bp = Blueprint("gdpr", __name__)


@bp.get("/export")
@jwt_required()
def export_data():
    uid = int(get_jwt_identity())
    zip_bytes = export_user_data(uid)
    return send_file(
        io.BytesIO(zip_bytes),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"finmind-export-{uid}.zip",
    )


@bp.delete("/account")
@jwt_required()
def delete_account():
    uid = int(get_jwt_identity())
    record = delete_user_account(uid)
    return jsonify({"message": "Account permanently deleted.", "audit": record}), 200
