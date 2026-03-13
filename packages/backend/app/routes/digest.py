"""API routes for weekly financial digest."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import generate_weekly_digest, generate_digest_email_body
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial digest.

    Query parameters:
        week_of: ISO date within the target week (default: previous week)

    Headers:
        X-Gemini-Api-Key: optional Gemini key for AI-enhanced narrative
        X-Insight-Persona: optional AI persona override
    """
    uid = int(get_jwt_identity())
    week_of_str = request.args.get("week_of", "").strip()
    week_of = date.fromisoformat(week_of_str) if week_of_str else None

    gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    digest = generate_weekly_digest(
        uid,
        week_of=week_of,
        gemini_api_key=gemini_key,
        persona=persona,
    )
    logger.info("Weekly digest served user=%s", uid)
    return jsonify(digest)


@bp.get("/weekly/email-preview")
@jwt_required()
def weekly_digest_email_preview():
    """Generate digest and return as formatted email text.

    Useful for previewing what the digest email will look like.
    """
    uid = int(get_jwt_identity())
    week_of_str = request.args.get("week_of", "").strip()
    week_of = date.fromisoformat(week_of_str) if week_of_str else None

    gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    digest = generate_weekly_digest(
        uid, week_of=week_of, gemini_api_key=gemini_key, persona=persona,
    )
    email_body = generate_digest_email_body(digest)
    return jsonify(email_body=email_body, digest=digest)
