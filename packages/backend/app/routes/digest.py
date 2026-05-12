from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import DigestPreference
from ..services.digest import generate_weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    digest = generate_weekly_digest(uid)
    logger.info("Weekly digest served user=%s", uid)
    return jsonify(digest)


@bp.get("/preferences")
@jwt_required()
def get_preferences():
    uid = int(get_jwt_identity())
    pref = db.session.query(DigestPreference).filter_by(user_id=uid).first()
    if not pref:
        return jsonify(enabled=True, day_of_week=0, send_email=True)
    return jsonify(
        enabled=pref.enabled,
        day_of_week=pref.day_of_week,
        send_email=pref.send_email,
    )


@bp.put("/preferences")
@jwt_required()
def update_preferences():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    pref = db.session.query(DigestPreference).filter_by(user_id=uid).first()
    if not pref:
        pref = DigestPreference(user_id=uid)
        db.session.add(pref)
    if "enabled" in data:
        pref.enabled = bool(data["enabled"])
    if "day_of_week" in data:
        dow = int(data["day_of_week"])
        if dow < 0 or dow > 6:
            return jsonify(error="day_of_week must be 0-6"), 400
        pref.day_of_week = dow
    if "send_email" in data:
        pref.send_email = bool(data["send_email"])
    db.session.commit()
    logger.info("Digest preferences updated user=%s", uid)
    return jsonify(
        enabled=pref.enabled,
        day_of_week=pref.day_of_week,
        send_email=pref.send_email,
    )
