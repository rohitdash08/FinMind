"""Routes for Smart Digest — weekly financial summaries."""

from __future__ import annotations

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.cache import cache_get, cache_set
from ..services.smart_digest import generate_weekly_digest, parse_week_param

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

DIGEST_CACHE_TTL = 600  # 10 minutes


def _digest_cache_key(user_id: int, iso_year: int, iso_week: int) -> str:
    return f"user:{user_id}:digest:{iso_year}-W{iso_week:02d}"


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return the weekly financial digest for the authenticated user.

    Query params:
        week (str, optional): ISO week in ``YYYY-Www`` format (e.g. ``2026-W14``).
            Defaults to the current week.

    Headers:
        X-Gemini-Api-Key (str, optional): User-supplied Gemini API key.
        X-Insight-Persona (str, optional): Custom AI persona prompt.

    Returns:
        200: JSON digest payload.
        400: Invalid week parameter.
    """
    uid = int(get_jwt_identity())
    week_param = request.args.get("week", "").strip() or None

    try:
        iso_year, iso_week = parse_week_param(week_param)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    # Check cache (only for non-AI-customised requests)
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None
    persona = (request.headers.get("X-Insight-Persona") or "").strip() or None

    cache_key = _digest_cache_key(uid, iso_year, iso_week)
    if not user_gemini_key and not persona:
        cached = cache_get(cache_key)
        if cached:
            logger.debug("Digest cache hit user=%s week=%d-W%02d", uid, iso_year, iso_week)
            return jsonify(cached)

    digest = generate_weekly_digest(
        user_id=uid,
        iso_year=iso_year,
        iso_week=iso_week,
        gemini_api_key=user_gemini_key,
        persona=persona,
    )

    # Cache only default (non-custom) digests
    if not user_gemini_key and not persona:
        cache_set(cache_key, digest, ttl_seconds=DIGEST_CACHE_TTL)

    return jsonify(digest)
