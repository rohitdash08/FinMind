from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion, weekly_digest
from ..services.cache import (
    cache_get,
    cache_set,
    weekly_digest_key,
    WEEKLY_DIGEST_TTL,
)
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
def get_weekly_digest():
    """
    Return a weekly financial summary digest.

    Query Parameters
    ----------------
    week : str, optional
        ISO week string in ``YYYY-WNN`` format (e.g. ``2026-W11``).
        Defaults to the current calendar week.

    Returns
    -------
    JSON with the weekly digest payload:
      - week, period (start/end)
      - total_spent, total_income, net_flow
      - week_over_week_change_pct, previous_week_spent
      - category_breakdown (with wow_change_pct per category)
      - daily_breakdown (one entry per day)
      - top_expenses (up to 5 largest individual expenses)
      - insights (plain-English observations)
      - transaction_count
    """
    uid = int(get_jwt_identity())
    week_param = (request.args.get("week") or "").strip() or None

    # Validate week format early before cache lookup
    if week_param:
        parts = week_param.split("-W")
        if len(parts) != 2:
            return (
                jsonify(
                    {
                        "error": "invalid_week_format",
                        "message": (
                            f"Invalid week '{week_param}'. "
                            "Expected format: YYYY-WNN (e.g. 2026-W11)."
                        ),
                    }
                ),
                400,
            )
        try:
            year, wnum = int(parts[0]), int(parts[1])
            if not (1 <= wnum <= 53):
                raise ValueError
        except ValueError:
            return (
                jsonify(
                    {
                        "error": "invalid_week_format",
                        "message": (
                            f"Invalid week '{week_param}'. "
                            "Expected format: YYYY-WNN (e.g. 2026-W11)."
                        ),
                    }
                ),
                400,
            )

    # Try cache (best-effort; Redis failures are non-fatal)
    cache_key = weekly_digest_key(uid, week_param or "current")
    try:
        cached = cache_get(cache_key)
        if cached is not None:
            logger.debug("Weekly digest cache hit user=%s week=%s", uid, week_param)
            return jsonify(cached)
    except Exception:
        pass

    try:
        digest = weekly_digest(uid, week_param)
    except ValueError as exc:
        return jsonify({"error": "invalid_week_format", "message": str(exc)}), 400

    # Persist to cache (best-effort)
    try:
        cache_set(cache_key, digest, ttl_seconds=WEEKLY_DIGEST_TTL)
    except Exception:
        pass

    logger.info(
        "Weekly digest served user=%s week=%s total_spent=%s",
        uid,
        digest["week"],
        digest["total_spent"],
    )
    return jsonify(digest)
