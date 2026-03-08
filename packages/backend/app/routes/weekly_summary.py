"""Routes for the weekly financial digest."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.weekly_summary import generate_weekly_summary
import logging

bp = Blueprint("weekly_summary", __name__)
logger = logging.getLogger("finmind.weekly_summary")


@bp.get("")
@jwt_required()
def get_weekly_summary():
    """Return the weekly financial digest.

    Query params:
        week_of (str, optional): ISO date (YYYY-MM-DD) identifying the week.
            Defaults to the current week.
    """
    uid = int(get_jwt_identity())
    week_of_raw = request.args.get("week_of")
    week_of: date | None = None
    if week_of_raw:
        try:
            week_of = date.fromisoformat(week_of_raw)
        except ValueError:
            return jsonify(error="invalid week_of, expected YYYY-MM-DD"), 400

    summary = generate_weekly_summary(uid, week_of)
    logger.info("Weekly summary served user=%s week=%s", uid, summary["week"]["start"])
    return jsonify(summary)
