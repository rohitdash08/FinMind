"""
Weekly digest API routes.
"""
from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest
from ..services.cache import cache_get, cache_set
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _get_current_week() -> str:
    """Get current week in YYYY-WNN format."""
    today = date.today()
    iso_calendar = today.isocalendar()
    return f"{iso_calendar[0]}-W{iso_calendar[1]:02d}"


def _digest_cache_key(uid: int, week: str) -> str:
    """Generate cache key for weekly digest."""
    return f"user:{uid}:digest:weekly:{week}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """
    Get weekly financial digest with trends and insights.
    
    Query Parameters:
        week (optional): Week in format YYYY-WNN (e.g., "2026-W08").
                        Defaults to current week.
    
    Headers:
        X-Gemini-Api-Key (optional): User's Gemini API key for AI insights
    
    Returns:
        JSON object containing:
        - period: Week information (week, start_date, end_date)
        - expenses: Total income, expenses, net flow, category breakdown, daily pattern
        - bills: Bills due during the week
        - comparison: Week-over-week comparison
        - insights: AI-generated or heuristic insights
        - generated_at: Timestamp of digest generation
        - insight_method: "gemini" or "heuristic"
    
    Example:
        GET /digest/weekly?week=2026-W08
        
        Response:
        {
            "period": {
                "week": "2026-W08",
                "start_date": "2026-02-16",
                "end_date": "2026-02-22"
            },
            "expenses": {
                "total_income": 5000.00,
                "total_expenses": 3200.50,
                "net_flow": 1799.50,
                "categories": [...],
                "daily_spending": [...]
            },
            "bills": {
                "count": 2,
                "total_amount": 450.00,
                "bills": [...]
            },
            "comparison": {
                "current_week_expenses": 3200.50,
                "previous_week_expenses": 2800.00,
                "change_amount": 400.50,
                "change_percentage": 14.30
            },
            "insights": [
                "Great job! You saved 1799.50 this week.",
                "Your spending increased by 14.3% compared to last week."
            ],
            "generated_at": "2026-02-24T16:00:00",
            "insight_method": "heuristic"
        }
    """
    uid = int(get_jwt_identity())
    week = (request.args.get("week") or _get_current_week()).strip()
    
    # Validate week format
    try:
        if not week or len(week) != 8 or week[4] != "-" or week[5] != "W":
            return jsonify(
                error="Invalid week format. Expected YYYY-WNN (e.g., 2026-W08)"
            ), 400
        
        year = int(week[:4])
        week_num = int(week[6:])
        
        if not (1 <= week_num <= 53):
            return jsonify(error="Week number must be between 1 and 53"), 400
            
    except (ValueError, IndexError):
        return jsonify(
            error="Invalid week format. Expected YYYY-WNN (e.g., 2026-W08)"
        ), 400
    
    # Check cache
    cache_key = _digest_cache_key(uid, week)
    cached = cache_get(cache_key)
    if cached:
        logger.info("Weekly digest served from cache user=%s week=%s", uid, week)
        return jsonify(cached)
    
    # Get Gemini API key from header
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    
    try:
        digest = generate_weekly_digest(uid, week, gemini_api_key=user_gemini_key)
        
        # Cache for 1 hour (3600 seconds)
        cache_set(cache_key, digest, ttl_seconds=3600)
        
        logger.info(
            "Weekly digest generated user=%s week=%s method=%s",
            uid,
            week,
            digest.get("insight_method", "unknown"),
        )
        
        return jsonify(digest)
        
    except ValueError as e:
        logger.warning("Invalid week parameter user=%s week=%s error=%s", uid, week, e)
        return jsonify(error=str(e)), 400
        
    except Exception as e:
        logger.error(
            "Failed to generate weekly digest user=%s week=%s error=%s",
            uid,
            week,
            e,
            exc_info=True,
        )
        return jsonify(error="Failed to generate weekly digest"), 500
