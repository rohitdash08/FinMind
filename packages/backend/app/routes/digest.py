"""Weekly digest endpoint -- GET /digest/weekly."""

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import get_weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return a weekly financial digest.

    Query params
    ------------
    week : str, optional
        ISO week in ``YYYY-WNN`` format (e.g. ``2026-W15``).
        Defaults to the current week.
    """
    uid = int(get_jwt_identity())
    week = (request.args.get("week") or "").strip()

    if not week:
        today = date.today()
        iso = today.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"

    try:
        result = get_weekly_digest(uid, week)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    logger.info("Weekly digest served user=%s week=%s", uid, week)
    return jsonify(result)
