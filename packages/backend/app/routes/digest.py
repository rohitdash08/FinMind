"""Digest endpoints for weekly financial summaries."""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..extensions import db
from ..models import WeeklyDigest
from ..services.cache import cache_get, cache_set
from ..services.digest import (
    deliver_digest_email,
    get_or_create_digest,
    week_boundaries,
)

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _weekly_digest_cache_key(user_id: int, week_start: str) -> str:
    return f"user:{user_id}:weekly_digest:{week_start}"


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return digest for the current or specified week."""
    uid = int(get_jwt_identity())
    week_start_param = (request.args.get("week_start") or "").strip()
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None

    if week_start_param:
        try:
            w_start = date.fromisoformat(week_start_param)
        except ValueError:
            return jsonify(error="invalid week_start, expected YYYY-MM-DD"), 400
    else:
        w_start, _ = week_boundaries()

    cache_key = _weekly_digest_cache_key(uid, w_start.isoformat())
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    digest_data = get_or_create_digest(
        uid, w_start=w_start, gemini_api_key=user_gemini_key
    )

    cache_set(cache_key, digest_data, ttl_seconds=3600)
    logger.info("Weekly digest served user=%s week=%s", uid, w_start)
    return jsonify(digest_data)


@bp.get("/weekly/history")
@jwt_required()
def digest_history():
    """List past weekly digests for the authenticated user."""
    uid = int(get_jwt_identity())
    limit = min(int(request.args.get("limit", 10)), 52)

    digests = (
        db.session.query(WeeklyDigest)
        .filter_by(user_id=uid)
        .order_by(WeeklyDigest.week_start.desc())
        .limit(limit)
        .all()
    )

    result = [
        {
            "id": d.id,
            "week_start": d.week_start.isoformat(),
            "week_end": d.week_end.isoformat(),
            "total_expenses": (
                d.payload.get("summary", {}).get("total_expenses", 0)
                if d.payload
                else 0
            ),
            "net_flow": (
                d.payload.get("summary", {}).get("net_flow", 0) if d.payload else 0
            ),
            "method": d.method,
            "delivered_at": (d.delivered_at.isoformat() if d.delivered_at else None),
            "created_at": d.created_at.isoformat(),
        }
        for d in digests
    ]
    return jsonify(result)


@bp.post("/weekly/send")
@jwt_required()
def send_weekly_digest():
    """Generate (if needed) and send digest email for the current user."""
    uid = int(get_jwt_identity())
    user_gemini_key = (request.headers.get("X-Gemini-Api-Key") or "").strip() or None

    w_start, _ = week_boundaries()
    digest_data = get_or_create_digest(
        uid, w_start=w_start, gemini_api_key=user_gemini_key
    )
    sent = deliver_digest_email(uid, digest_data)
    logger.info("Digest send user=%s digest=%s sent=%s", uid, digest_data["id"], sent)
    return jsonify(sent=sent, digest_id=digest_data["id"])
