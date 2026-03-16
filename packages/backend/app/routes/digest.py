"""Weekly digest endpoints."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import compute_digest, generate_narrative
from ..services.cache import cache_get, cache_set

bp = Blueprint("digest", __name__)


def _current_iso_week() -> str:
    y, w, _ = date.today().isocalendar()
    return f"{y}-W{w:02d}"


def _is_valid_week(w: str) -> bool:
    try:
        year_s, week_s = w.split("-W")
        year, week = int(year_s), int(week_s)
        return 2000 <= year <= 2100 and 1 <= week <= 53
    except Exception:
        return False


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return the weekly financial digest for the authenticated user."""
    uid = int(get_jwt_identity())
    week = (request.args.get("week") or _current_iso_week()).strip()
    if not _is_valid_week(week):
        return jsonify(error="invalid week, expected YYYY-Wnn (e.g. 2026-W11)"), 400

    cache_key = f"user:{uid}:weekly_digest:{week}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    digest = compute_digest(uid, week)
    narrative = generate_narrative(digest)
    digest["narrative"] = narrative

    cache_set(cache_key, digest, ttl_seconds=3600)
    return jsonify(digest)


@bp.get("/weekly/history")
@jwt_required()
def digest_history():
    """Return digests for the last *n* weeks (default 4)."""
    uid = int(get_jwt_identity())
    count = min(int(request.args.get("count", 4)), 12)

    results = []
    week = _current_iso_week()
    for _ in range(count):
        d = compute_digest(uid, week)
        d["narrative"] = generate_narrative(d)
        results.append(d)
        # Navigate to previous week
        year_s, week_s = week.split("-W")
        y, w = int(year_s), int(week_s)
        if w == 1:
            y -= 1
            w = 52
        else:
            w -= 1
        week = f"{y}-W{w:02d}"

    return jsonify(results)
