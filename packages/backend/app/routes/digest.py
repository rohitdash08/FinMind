"""Weekly digest API endpoints.

Provides endpoints for generating smart weekly financial summaries
with trends, insights, and breakdowns.
"""

from datetime import date, timedelta
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest
from ..services.cache import cache_get, cache_set

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _digest_cache_key(uid: int, week_start: str) -> str:
    """Generate cache key for weekly digest."""
    return f"digest:weekly:{uid}:{week_start}"


def _parse_week_start(week_str: str | None) -> date | None:
    """Parse week start date from string, return None for current week."""
    if not week_str:
        return None
    
    try:
        parsed = date.fromisoformat(week_str.strip())
        # Normalize to Monday
        return parsed - timedelta(days=parsed.weekday())
    except ValueError:
        return None


def _is_valid_week(week_str: str) -> bool:
    """Validate week start string format (YYYY-MM-DD)."""
    if not week_str or len(week_str) != 10:
        return False
    try:
        date.fromisoformat(week_str)
        return True
    except ValueError:
        return False


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Get weekly financial digest.
    
    Query Parameters:
        week: Optional week start date (YYYY-MM-DD). Defaults to current week.
              The date will be normalized to the Monday of that week.
    
    Headers:
        X-Gemini-Api-Key: Optional user-provided Gemini API key for AI insights
        X-Insight-Persona: Optional custom persona for AI insights
    
    Returns:
        JSON object containing:
        - period: Week date range and number
        - summary: Total income, expenses, net flow
        - trends: Week-over-week comparisons
        - category_breakdown: Spending by category
        - daily_breakdown: Daily spending totals
        - upcoming_bills: Bills due this week
        - top_transactions: Largest transactions
        - insights: AI or heuristic-generated insights
    """
    uid = int(get_jwt_identity())
    week_param = request.args.get("week", "").strip()
    
    # Validate week parameter if provided
    if week_param and not _is_valid_week(week_param):
        return jsonify(error="Invalid week format. Expected YYYY-MM-DD."), 400
    
    week_start = _parse_week_start(week_param)
    
    # Generate cache key
    week_key = (
        week_start.isoformat()
        if week_start
        else (date.today() - timedelta(days=date.today().weekday())).isoformat()
    )
    cache_key = _digest_cache_key(uid, week_key)
    
    # Check cache
    cached = cache_get(cache_key)
    if cached:
        logger.debug("Weekly digest cache hit user=%s week=%s", uid, week_key)
        return jsonify(cached)
    
    # Get optional headers
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    
    # Generate digest
    digest = generate_weekly_digest(
        uid=uid,
        week_start=week_start,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    
    # Cache for 5 minutes (300 seconds)
    cache_set(cache_key, digest, ttl_seconds=300)
    
    logger.info("Weekly digest generated user=%s week=%s", uid, week_key)
    return jsonify(digest)


@bp.get("/weekly/summary")
@jwt_required()
def weekly_summary():
    """Get a condensed weekly summary (lighter endpoint).
    
    Returns only the summary and trends without detailed breakdowns.
    Useful for quick dashboard widgets or notifications.
    
    Query Parameters:
        week: Optional week start date (YYYY-MM-DD). Defaults to current week.
    
    Returns:
        JSON object containing:
        - period: Week date range
        - summary: Total income, expenses, net flow
        - trends: Week-over-week comparisons
        - highlight: One-sentence summary
    """
    uid = int(get_jwt_identity())
    week_param = request.args.get("week", "").strip()
    
    if week_param and not _is_valid_week(week_param):
        return jsonify(error="Invalid week format. Expected YYYY-MM-DD."), 400
    
    week_start = _parse_week_start(week_param)
    
    # Generate full digest (will use cache if available)
    digest = generate_weekly_digest(uid=uid, week_start=week_start)
    
    # Return condensed version
    condensed = {
        "period": digest["period"],
        "summary": digest["summary"],
        "trends": digest["trends"],
        "highlight": digest.get("insights", {}).get("highlight", ""),
    }
    
    return jsonify(condensed)
