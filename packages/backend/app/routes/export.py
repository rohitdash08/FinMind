"""Secure backup & encrypted export routes."""

import logging
from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.secure_export import export_user_data, encrypt_data, decrypt_data

bp = Blueprint("export", __name__)
logger = logging.getLogger("finmind.export")


@bp.get("")
@jwt_required()
def export_data():
    """Export user data as JSON or CSV.

    Query params:
        format (str): json or csv (default json).
        encrypted (bool): If true, requires passphrase param.
        passphrase (str): Encryption passphrase (required if encrypted=true).
    """
    uid = int(get_jwt_identity())
    fmt = (request.args.get("format") or "json").lower()
    if fmt not in ("json", "csv"):
        return jsonify(error="format must be json or csv"), 400

    want_encrypted = request.args.get("encrypted", "").lower() in ("true", "1", "yes")
    passphrase = request.args.get("passphrase", "").strip()

    if want_encrypted and not passphrase:
        return jsonify(error="passphrase required for encrypted export"), 400
    if want_encrypted and len(passphrase) < 8:
        return jsonify(error="passphrase must be at least 8 characters"), 400

    result = export_user_data(uid, fmt=fmt)

    if want_encrypted:
        encrypted = encrypt_data(result["data"], passphrase)
        encrypted["exported_at"] = result["exported_at"]
        encrypted["original_format"] = fmt
        return jsonify(encrypted)

    if fmt == "csv":
        return Response(
            result["data"],
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=finmind-export.csv"},
        )

    return jsonify({"data": result["data"], "format": fmt, "exported_at": result["exported_at"]})


@bp.post("/decrypt")
@jwt_required()
def decrypt():
    """Decrypt a previously encrypted export.

    Body: { encrypted payload + passphrase }
    """
    payload = request.get_json() or {}
    passphrase = payload.get("passphrase", "")
    if not passphrase:
        return jsonify(error="passphrase required"), 400

    required = ["ciphertext", "salt", "iv", "tag"]
    if not all(k in payload for k in required):
        return jsonify(error=f"missing fields: {required}"), 400

    try:
        plaintext = decrypt_data(payload, passphrase)
        return jsonify({"data": plaintext, "format": payload.get("original_format", "json")})
    except Exception as e:
        logger.warning("Decrypt failed: %s", e)
        return jsonify(error="decryption failed — wrong passphrase?"), 400
