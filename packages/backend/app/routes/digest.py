from datetime import date, timedelta
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest, get_digest_history

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


def _parse_week_start(date_str: str) -> date | None:
    """Parse an ISO date string and return the Monday of that week."""
    try:
        d = date.fromisoformat(date_str)
        return d - timedelta(days=d.weekday())
    except (ValueError, TypeError):
        return None


@bp.get("/weekly")
@jwt_required()
def weekly_current():
    """Return the current week's digest, generating if it does not exist."""
    uid = int(get_jwt_identity())
    digest = generate_weekly_digest(uid)
    return jsonify(digest)


@bp.get("/weekly/<string:date_str>")
@jwt_required()
def weekly_by_date(date_str: str):
    """Return the digest for the week containing the given date."""
    uid = int(get_jwt_identity())
    week_start = _parse_week_start(date_str)
    if week_start is None:
        return jsonify(error="Invalid date format. Use YYYY-MM-DD."), 400
    digest = generate_weekly_digest(uid, week_start=week_start)
    return jsonify(digest)


@bp.get("/history")
@jwt_required()
def history():
    """Return past weekly digests for the authenticated user."""
    uid = int(get_jwt_identity())
    limit_str = request.args.get("limit", "10")
    try:
        limit = max(1, min(50, int(limit_str)))
    except (ValueError, TypeError):
        limit = 10
    digests = get_digest_history(uid, limit=limit)
    return jsonify(digests)


@bp.post("/generate")
@jwt_required()
def force_generate():
    """Force regenerate the current week's digest."""
    uid = int(get_jwt_identity())
    week_start_str = request.args.get("week_start")
    week_start = _parse_week_start(week_start_str) if week_start_str else None
    digest = generate_weekly_digest(uid, week_start=week_start, force=True)
    logger.info("Digest force-regenerated user=%s", uid)
    return jsonify(digest), 201
