"""
Weekly Digest API Routes
=========================

Endpoints for generating and retrieving weekly financial digests.

GET /digest/weekly      — Generate digest for the most recent complete week
GET /digest/weekly?date=2026-04-28  — Generate digest for the week containing that date
GET /digest/history     — List previously generated digests (last 12 weeks)
"""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate a weekly financial digest.

    Query params:
        date (optional): ISO date string. The digest covers the full week
                         (Mon-Sun) prior to this date. Defaults to today.

    Headers:
        X-Gemini-Api-Key (optional): Override Gemini API key for AI narrative.
        X-Insight-Persona (optional): Custom persona for the AI narrative.

    Returns:
        JSON digest with summary, category breakdown, anomalies, narrative, etc.
    """
    uid = int(get_jwt_identity())
    date_param = request.args.get("date")
    reference_date = None
    if date_param:
        try:
            reference_date = date.fromisoformat(date_param.strip())
        except ValueError:
            return jsonify(error="invalid date format, use YYYY-MM-DD"), 400

    gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    digest = generate_digest(
        uid=uid,
        reference_date=reference_date,
        gemini_api_key=gemini_key,
        persona=persona,
    )
    logger.info(
        "Weekly digest served user=%s period=%s-%s",
        uid,
        digest["period"]["start"],
        digest["period"]["end"],
    )
    return jsonify(digest)


@bp.get("/highlights")
@jwt_required()
def digest_highlights():
    """Return just the key highlights — lighter payload for dashboard cards.

    Returns:
        JSON with: total_spent, trend, change_pct, top_category, narrative (short).
    """
    uid = int(get_jwt_identity())
    date_param = request.args.get("date")
    reference_date = None
    if date_param:
        try:
            reference_date = date.fromisoformat(date_param.strip())
        except ValueError:
            return jsonify(error="invalid date format, use YYYY-MM-DD"), 400

    digest = generate_digest(uid=uid, reference_date=reference_date)

    highlights = {
        "period": digest["period"],
        "total_spent": digest["summary"]["total_spent"],
        "net_flow": digest["summary"]["net_flow"],
        "trend": digest["comparison"]["trend"],
        "change_pct": digest["comparison"]["change_pct"],
        "top_category": digest["by_category"][0] if digest["by_category"] else None,
        "anomaly_count": len(digest["anomalies"]),
        "narrative": digest["narrative"],
    }
    return jsonify(highlights)
