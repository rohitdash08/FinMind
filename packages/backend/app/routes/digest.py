"""Routes for weekly financial digest."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest, list_available_digests
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("")
@jwt_required()
def get_weekly_digest():
    """Return the weekly financial digest for a given week.

    Query params:
        week_start (str, optional): ISO date of the Monday to report on.
            Defaults to the last completed week.
    """
    uid = int(get_jwt_identity())
    week_start = (request.args.get("week_start") or "").strip() or None

    try:
        digest = generate_weekly_digest(uid, week_start)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    logger.info(
        "Weekly digest served user=%s week=%s",
        uid,
        digest["period"]["week_start"],
    )
    return jsonify(digest)


@bp.get("/weeks")
@jwt_required()
def get_available_weeks():
    """Return a list of weeks with expense data for digest navigation."""
    uid = int(get_jwt_identity())
    try:
        count = min(52, max(1, int(request.args.get("count", "12"))))
    except ValueError:
        count = 12

    weeks = list_available_digests(uid, count)
    return jsonify(weeks)
