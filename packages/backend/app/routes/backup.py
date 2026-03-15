"""Backup and encrypted export routes."""

import logging

from flask import Blueprint, jsonify, request, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from io import BytesIO

from ..extensions import db
from ..services.backup import (
    build_export_data,
    export_to_json,
    export_to_csv,
    encrypt_export,
    decrypt_export,
    DecryptionError,
)

bp = Blueprint("backup", __name__)
logger = logging.getLogger("finmind.backup")


@bp.get("/export")
@jwt_required()
def export_backup():
    """Export all user data in JSON or CSV format.

    Query params:
      - format: 'json' (default) or 'csv'
      - encrypt: 'true' to encrypt the export (requires 'passphrase' header)
      - passphrase: (via header X-Backup-Passphrase) encryption key

    Returns the export as a downloadable file.
    """
    uid = int(get_jwt_identity())
    fmt = request.args.get("format", "json").lower()
    do_encrypt = request.args.get("encrypt", "false").lower() == "true"

    if fmt not in ("json", "csv"):
        return jsonify(error="format must be 'json' or 'csv'"), 400

    try:
        data = build_export_data(uid, db.session)
    except Exception as exc:
        logger.error("Export failed user=%s: %s", uid, exc)
        return jsonify(error="export failed"), 500

    if fmt == "csv":
        content = export_to_csv(data)
        ext = "csv"
        mime = "text/csv"
    else:
        content = export_to_json(data)
        ext = "json"
        mime = "application/json"

    if do_encrypt:
        passphrase = request.headers.get("X-Backup-Passphrase")
        if not passphrase:
            return jsonify(error="passphrase required for encryption"), 400
        if len(passphrase) < 8:
            return jsonify(error="passphrase must be at least 8 characters"), 400

        result = encrypt_export(content, passphrase)
        import json as _json

        content = _json.dumps(result, indent=2)
        ext = "enc.json"
        mime = "application/json"

    filename = f"finmind_backup_{uid}_{ext}"
    buf = BytesIO(content.encode("utf-8"))
    buf.seek(0)

    logger.info("Export user=%s format=%s encrypted=%s", uid, fmt, do_encrypt)
    return send_file(buf, mimetype=mime, as_attachment=True, download_name=filename)


@bp.post("/decrypt")
@jwt_required()
def decrypt_backup():
    """Decrypt an encrypted backup file.

    Expects JSON body:
      - encrypted_data: base64-encoded encrypted payload
      - passphrase: decryption key

    Returns the decrypted JSON content.
    """
    body = request.get_json(silent=True) or {}
    encrypted_b64 = body.get("encrypted_data")
    passphrase = body.get("passphrase")

    if not encrypted_b64 or not passphrase:
        return jsonify(error="encrypted_data and passphrase required"), 400

    try:
        decrypted = decrypt_export(encrypted_b64, passphrase)
    except DecryptionError as exc:
        logger.warning("Decryption failed user=%s: %s", get_jwt_identity(), exc)
        return jsonify(error="decryption failed — wrong passphrase or corrupted data"), 400

    return jsonify(decrypted=decrypted), 200


@bp.get("/export/summary")
@jwt_required()
def export_summary():
    """Get a summary of data available for export (preview without data).

    Returns record counts per table.
    """
    uid = int(get_jwt_identity())

    try:
        data = build_export_data(uid, db.session)
        summary = {table: len(rows) for table, rows in data.items()}
    except Exception as exc:
        logger.error("Export summary failed user=%s: %s", uid, exc)
        return jsonify(error="summary generation failed"), 500

    return jsonify(summary=summary, user_id=uid), 200
