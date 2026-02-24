"""
export.py — Secure data export endpoints.

GET /export/json                           — download all data as JSON
GET /export/json?encrypted=true&passphrase=X   — AES-256 encrypted JSON
GET /export/csv                            — download ZIP of CSVs
GET /export/csv?encrypted=true&passphrase=X    — AES-256 encrypted ZIP

All endpoints require a valid JWT (Bearer token).
"""
import logging
from datetime import datetime

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..services.export import (
    encrypt_payload,
    export_user_csv_zip,
    export_user_json,
)

bp_export = Blueprint("export", __name__)
logger = logging.getLogger("finmind.export_routes")


@bp_export.get("/json")
@jwt_required()
def download_json():
    """Export all user data as JSON (optionally AES-256 encrypted)."""
    uid = int(get_jwt_identity())
    encrypted = request.args.get("encrypted", "false").lower() == "true"
    passphrase = request.args.get("passphrase", "")

    if encrypted and not passphrase:
        return jsonify(error="passphrase required for encrypted export"), 400

    payload = export_user_json(uid, db.session)
    filename = f"finmind_export_{uid}_{datetime.utcnow().strftime('%Y%m%d')}"

    if encrypted:
        payload = encrypt_payload(payload, passphrase)
        filename += ".enc"
        mimetype = "application/octet-stream"
    else:
        filename += ".json"
        mimetype = "application/json"

    logger.info(
        "JSON export user=%s encrypted=%s size=%d", uid, encrypted, len(payload)
    )
    return Response(
        payload,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@bp_export.get("/csv")
@jwt_required()
def download_csv():
    """Export all user data as a ZIP of CSVs (optionally AES-256 encrypted)."""
    uid = int(get_jwt_identity())
    encrypted = request.args.get("encrypted", "false").lower() == "true"
    passphrase = request.args.get("passphrase", "")

    if encrypted and not passphrase:
        return jsonify(error="passphrase required for encrypted export"), 400

    payload = export_user_csv_zip(uid, db.session)
    filename = f"finmind_export_{uid}_{datetime.utcnow().strftime('%Y%m%d')}"

    if encrypted:
        payload = encrypt_payload(payload, passphrase)
        filename += "_csv.enc"
        mimetype = "application/octet-stream"
    else:
        filename += ".zip"
        mimetype = "application/zip"

    logger.info(
        "CSV export user=%s encrypted=%s size=%d", uid, encrypted, len(payload)
    )
    return Response(
        payload,
        mimetype=mimetype,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
