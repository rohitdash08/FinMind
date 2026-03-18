"""Weekly financial digest API routes."""

import logging
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest, generate_trends

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial digest for the authenticated user.

    Query params:
        week_offset (int): 0 = current week (default), -1 = last week, etc.
    """
    uid = int(get_jwt_identity())

    raw_offset = request.args.get("week_offset", "0").strip()
    try:
        week_offset = int(raw_offset)
    except (ValueError, TypeError):
        return jsonify(error="week_offset must be an integer"), 400

    if week_offset > 0:
        return jsonify(error="week_offset must be 0 or negative (past weeks)"), 400
    if week_offset < -52:
        return jsonify(error="week_offset cannot go back more than 52 weeks"), 400

    user_gemini_key = (
        (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    )

    try:
        digest = generate_weekly_digest(
            uid,
            week_offset=week_offset,
            gemini_api_key=user_gemini_key,
        )
        logger.info(
            "Weekly digest served user=%s week_offset=%s", uid, week_offset
        )
        return jsonify(digest)
    except Exception:
        logger.exception("Failed to generate weekly digest user=%s", uid)
        return jsonify(error="Failed to generate weekly digest"), 500


@bp.get("/trends")
@jwt_required()
def spending_trends():
    """Return spending trend data over multiple weeks.

    Query params:
        weeks (int): Number of weeks to include (4-12, default 8).
    """
    uid = int(get_jwt_identity())

    raw_weeks = request.args.get("weeks", "8").strip()
    try:
        weeks = int(raw_weeks)
    except (ValueError, TypeError):
        return jsonify(error="weeks must be an integer"), 400

    if weeks < 4 or weeks > 12:
        return jsonify(error="weeks must be between 4 and 12"), 400

    try:
        trends = generate_trends(uid, weeks=weeks)
        logger.info("Spending trends served user=%s weeks=%s", uid, weeks)
        return jsonify(trends)
    except Exception:
        logger.exception("Failed to generate spending trends user=%s", uid)
        return jsonify(error="Failed to generate spending trends"), 500
