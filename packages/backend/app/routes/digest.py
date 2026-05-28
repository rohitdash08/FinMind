"""Weekly smart digest endpoint for FinMind."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import generate_weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial summary digest.

    Query params:
      date (optional): Reference date in YYYY-MM-DD format. Defaults to today.
    Headers:
      X-Gemini-Api-Key (optional): User's Gemini API key for AI insights.
    """
    uid = int(get_jwt_identity())
    ref_date_str = (request.args.get("date") or "").strip()
    ref_date = None
    if ref_date_str:
        try:
            ref_date = date.fromisoformat(ref_date_str)
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None

    try:
        digest = generate_weekly_digest(
            uid,
            reference_date=ref_date,
            gemini_api_key=user_gemini_key,
        )
    except Exception:
        logger.exception("Digest generation failed user=%s", uid)
        return jsonify(error="failed to generate digest"), 500

    logger.info("Weekly digest served user=%s", uid)
    return jsonify(digest)
