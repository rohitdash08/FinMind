"""Digest API – weekly financial summary endpoints."""

from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.digest import generate_weekly_digest, format_digest_text
from ..services.reminders import send_email, send_whatsapp
from ..models import User
from ..extensions import db

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return the latest weekly digest for the authenticated user.

    Query params:
        ref_date – ISO date to anchor the week (defaults to today, giving last full week).
    """
    uid = int(get_jwt_identity())
    ref = request.args.get("ref_date")
    ref_date = date.fromisoformat(ref) if ref else None

    digest = generate_weekly_digest(uid, ref_date=ref_date)
    return jsonify(digest)


@bp.post("/weekly/send")
@jwt_required()
def send_weekly_digest():
    """Generate the digest and deliver it via email and/or WhatsApp.

    JSON body (all optional):
        ref_date  – ISO date
        email     – bool (default true)
        whatsapp  – str  phone number (e.g. whatsapp:+1234567890)
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}
    ref = data.get("ref_date")
    ref_date = date.fromisoformat(ref) if ref else None

    digest = generate_weekly_digest(uid, ref_date=ref_date)
    text = format_digest_text(digest)
    results = {"digest": digest, "delivery": {}}

    user = db.session.get(User, uid)
    user_email = user.email if user else None

    if data.get("email", True) and user_email:
        ok = send_email(user_email, "Your FinMind Weekly Digest", text)
        results["delivery"]["email"] = "sent" if ok else "failed"

    whatsapp_to = data.get("whatsapp")
    if whatsapp_to:
        ok = send_whatsapp(whatsapp_to, text)
        results["delivery"]["whatsapp"] = "sent" if ok else "failed"

    logger.info("Weekly digest delivered user=%s channels=%s", uid, list(results["delivery"].keys()))
    return jsonify(results)
