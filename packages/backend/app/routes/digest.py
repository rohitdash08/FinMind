"""
Weekly digest route for FinMind.

Endpoint:
    GET /digest/weekly

Returns a week-over-week financial summary for the authenticated user,
including category breakdown, spend trends, and plain-English insights.
Requires a valid JWT access token (Bearer).

Response is cached for 10 minutes per user to avoid redundant DB reads.
Cache is keyed on user ID + ISO week string so it auto-expires on rollover.
"""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..extensions import db
from ..models import User
from ..services.cache import cache_get, cache_set
from ..services.weekly_digest import build_weekly_digest, digest_to_dict

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

_CACHE_TTL = 600  # 10 minutes


def _digest_cache_key(uid: int, today: date, currency: str = "INR") -> str:
    iso = today.isocalendar()
    return f"user:{uid}:weekly_digest:{iso.year}:W{iso.week:02d}:{currency}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """
    Return a week-over-week financial digest for the current user.

    The current window is the 7 days ending today (inclusive).
    The prior window is the 7 days immediately before that.

    Response shape:
    {
      "generated_at": "YYYY-MM-DD",
      "user_id": <int>,
      "currency": "<str>",
      "current_week": {
        "week_start": "YYYY-MM-DD",
        "week_end":   "YYYY-MM-DD",
        "total_spend":  <float>,
        "total_income": <float>,
        "net_flow":     <float>,
        "categories": [
          {
            "category_id":   <int|null>,
            "category_name": <str>,
            "amount":        <float>,
            "share_pct":     <float>,
            "item_count":    <int>
          }, ...
        ]
      },
      "prior_week": { <same shape as current_week> },
      "total_spend_delta":      <float>,
      "total_spend_pct_change": <float|null>,
      "top_categories": [ { category_id, category_name, amount, share_pct }, ... ],
      "category_trends": [
        {
          "category_id":     <int|null>,
          "category_name":   <str>,
          "current_amount":  <float>,
          "prior_amount":    <float>,
          "delta":           <float>,
          "direction":       "UP"|"DOWN"|"FLAT"|"NEW"|"GONE",
          "pct_change":      <float|null>
        }, ...
      ],
      "insights": [ "<str>", ... ]
    }
    """
    uid = int(get_jwt_identity())
    today = date.today()

    user = db.session.get(User, uid)
    default_currency = user.preferred_currency if user else "INR"
    # Allow explicit override via ?currency=EUR (falls back to user preference)
    currency = (request.args.get("currency") or default_currency).upper()

    cache_key = _digest_cache_key(uid, today, currency)
    cached = cache_get(cache_key)
    if cached:
        logger.info("Weekly digest cache hit user=%s", uid)
        return jsonify(cached)

    digest = build_weekly_digest(
        uid=uid,
        session=db.session,
        reference_date=today,
        currency=currency,
    )
    payload = digest_to_dict(digest)

    cache_set(cache_key, payload, ttl_seconds=_CACHE_TTL)
    logger.info(
        "Weekly digest generated user=%s spend=%.2f delta=%.2f",
        uid,
        digest.current_week.total_spend,
        digest.total_spend_delta,
    )
    return jsonify(payload)
