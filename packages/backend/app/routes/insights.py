from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.weekly_digest import generate_weekly_digest, send_weekly_digest_email
from ..models import User
from ..extensions import db
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    logger.info("Budget suggestion served user=%s month=%s", uid, ym)
    return jsonify(suggestion)


@bp.get("/weekly-digest")
@jwt_required()
def weekly_digest():
    uid = int(get_jwt_identity())
    ref = request.args.get("date")
    ref_date = date.fromisoformat(ref) if ref else None
    digest = generate_weekly_digest(uid, ref_date)
    logger.info("Weekly digest served user=%s", uid)
    return jsonify(digest)


@bp.post("/weekly-digest/send")
@jwt_required()
def send_digest_email():
    uid = int(get_jwt_identity())
    user = db.session.get(User, uid)
    if not user:
        return jsonify(error="user not found"), 404
    ref = request.args.get("date")
    ref_date = date.fromisoformat(ref) if ref else None
    sent = send_weekly_digest_email(uid, user.email, ref_date)
    return jsonify(sent=sent)
