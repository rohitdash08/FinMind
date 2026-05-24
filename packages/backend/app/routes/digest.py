"""Digest routes.

GET  /digest/preview    – return this week's digest data as JSON (auth required)
POST /digest/send-test  – immediately email the digest to the authenticated user
"""
from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
import logging

from ..extensions import db
from ..models import User
from ..services.digest import build_weekly_digest, send_weekly_digest

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/preview")
@jwt_required()
def preview_digest():
    """Return the current week's digest data as JSON for the authenticated user."""
    uid = int(get_jwt_identity())
    data = build_weekly_digest(uid)
    logger.info("Digest preview requested by user=%s", uid)
    return jsonify(data), 200


@bp.post("/send-test")
@jwt_required()
def send_test_digest():
    """Immediately send a digest email to the authenticated user.

    Returns 200 when the email was dispatched via SMTP, or 202 when SMTP
    is not configured (digest was built but not sent).
    """
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404

    ok = send_weekly_digest(user)
    if ok:
        logger.info("Test digest sent to user=%s (%s)", uid, user.email)
        return jsonify(message="digest sent", email=user.email), 200

    logger.info("Test digest built but not sent (SMTP unconfigured) user=%s", uid)
    return jsonify(
        message="digest built but not sent — configure SMTP_URL to enable email delivery",
        email=user.email,
    ), 202
