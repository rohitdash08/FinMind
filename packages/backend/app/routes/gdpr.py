"""GDPR routes: PII export and account deletion.

GET  /gdpr/export          – download all personal data as a JSON file
POST /gdpr/delete-account  – permanently erase the account (password required)
"""
import json
from datetime import datetime, timezone

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.security import check_password_hash
import logging

from ..extensions import db
from ..models import User
from ..services.gdpr import build_export_package, delete_user_data

bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


@bp.get("/export")
@jwt_required()
def export_data():
    """Return the authenticated user's personal data as a downloadable JSON file.

    The response uses ``Content-Disposition: attachment`` so browsers
    save it directly rather than rendering it inline.
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    try:
        package = build_export_package(uid)
    except Exception:
        logger.exception("Export failed for user=%s", uid)
        return jsonify(error="export failed"), 500

    filename = (
        f"finmind-export-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    )
    payload = json.dumps(package, ensure_ascii=False, indent=2)

    logger.info("Data export served for user=%s", uid)
    return Response(
        payload,
        status=200,
        mimetype="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(payload.encode("utf-8"))),
        },
    )


@bp.post("/delete-account")
@jwt_required()
def delete_account():
    """Permanently delete the authenticated user's account and all associated data.

    Request body (JSON)
    -------------------
    password : str  – current password, required to confirm the irreversible action.

    Responses
    ---------
    204  – account successfully deleted
    400  – missing password field
    401  – password does not match
    404  – user not found
    500  – deletion error
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    data = request.get_json(silent=True) or {}
    password = (data.get("password") or "").strip()
    if not password:
        return jsonify(error="password required to confirm account deletion"), 400

    if not check_password_hash(user.password_hash, password):
        logger.warning("Delete-account password mismatch for user=%s", uid)
        return jsonify(error="incorrect password"), 401

    try:
        delete_user_data(uid)
    except Exception:
        logger.exception("Account deletion failed for user=%s", uid)
        return jsonify(error="deletion failed"), 500

    logger.info("Account permanently deleted for user=%s", uid)
    return "", 204
