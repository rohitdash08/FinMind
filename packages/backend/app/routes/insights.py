from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.ai import monthly_budget_suggestion
from ..services.cache import (
    TTL, budget_suggestion_key, cache_get, cache_set, get_cache_stats, reset_cache_stats
)
import logging

bp = Blueprint("insights", __name__)
logger = logging.getLogger("finmind.insights")


@bp.get("/budget-suggestion")
@jwt_required()
def budget_suggestion():
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    # AI results are expensive — cache for 30 minutes
    key = budget_suggestion_key(uid, ym)
    cached = cache_get(key)
    if cached is not None:
        logger.info("Budget suggestion cache HIT user=%s month=%s", uid, ym)
        return jsonify(cached)

    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None
    suggestion = monthly_budget_suggestion(
        uid,
        ym,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )
    cache_set(key, suggestion, ttl_seconds=TTL.AI_RESULT)
    logger.info("Budget suggestion served user=%s month=%s (cache MISS)", uid, ym)
    return jsonify(suggestion)


@bp.get("/cache-stats")
@jwt_required()
def cache_stats():
    """Return cache hit/miss stats and Redis memory usage.

    Access policy (deliberate): open to all authenticated users, no admin
    guard.  The data exposed (hit/miss counters, Redis memory usage) is
    operational telemetry with no PII; any logged-in user can consult it for
    debugging their own session behaviour.  If the deployment requires
    restricting this to admin roles, add a role check here (e.g.
    ``if get_jwt_identity_claims().get('role') != 'ADMIN': abort(403)``).
    """
    return jsonify(get_cache_stats())


@bp.delete("/cache-stats")
@jwt_required()
def clear_cache_stats():
    """Reset cache hit/miss counters.

    Same access policy as GET /cache-stats: open to all authenticated users.
    Counters are global (not per-user), so any user can reset them — acceptable
    for a lightweight monitoring tool.  Restrict to admin if needed (see above).
    """
    reset_cache_stats()
    return jsonify(message="cache stats reset")
