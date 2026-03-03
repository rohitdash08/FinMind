"""Routes for login anomaly detection & suspicious activity alerts."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.login_anomaly import get_login_history, get_suspicious_activity

bp = Blueprint("login_security", __name__)
logger = logging.getLogger("finmind.login_security")


@bp.get("/history")
@jwt_required()
def history():
    """Return recent login events for the authenticated user."""
    uid = int(get_jwt_identity())
    limit = request.args.get("limit", 20, type=int)
    limit = min(max(limit, 1), 100)
    return jsonify(get_login_history(uid, limit))


@bp.get("/suspicious")
@jwt_required()
def suspicious():
    """Return only flagged login events."""
    uid = int(get_jwt_identity())
    return jsonify(get_suspicious_activity(uid))
