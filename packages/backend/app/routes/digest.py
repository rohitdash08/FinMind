"""Weekly financial digest endpoint.

Provides ``GET /digest/weekly`` which returns a smart summary of the
user's financial activity for a given week, including category
breakdowns, daily trends, week-over-week comparisons, and
AI-generated narrative insights (Gemini with heuristic fallback).
"""

from datetime import date, datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.weekly_digest import generate_weekly_digest

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return the weekly financial digest for the authenticated user.

    Query params
    ------------
    week : str, optional
        ISO date (YYYY-MM-DD) of any day in the target week.
        Defaults to the most-recently completed full week.
    currency : str, optional
        Currency filter (informational label).

    Headers
    -------
    X-Gemini-Api-Key : str, optional
        Per-request Gemini API key override.
    X-Insight-Persona : str, optional
        AI persona override.
    """
    uid = int(get_jwt_identity())

    # Parse optional week parameter
    week_param = request.args.get("week", "").strip()
    week_start: date | None = None
    if week_param:
        try:
            week_start = datetime.strptime(week_param, "%Y-%m-%d").date()
        except ValueError:
            return jsonify(error="Invalid week format. Use YYYY-MM-DD."), 400

    currency = request.args.get("currency", "").strip() or None
    gemini_key = (
        request.headers.get("X-Gemini-Api-Key", "").strip() or None
    )
    persona = request.headers.get("X-Insight-Persona", "").strip() or None

    digest = generate_weekly_digest(
        uid,
        week_start=week_start,
        currency=currency,
        gemini_api_key=gemini_key,
        persona=persona,
    )
    return jsonify(digest), 200
