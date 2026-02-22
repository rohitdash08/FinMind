"""Weekly digest API routes."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """Return the weekly financial digest for the authenticated user.

    Query params:
        date (optional): ISO date string (YYYY-MM-DD) to get the digest for
                         the week containing that date. Defaults to current week.
    """
    uid = int(get_jwt_identity())
    date_str = request.args.get("date")
    target_date = date.fromisoformat(date_str) if date_str else None

    digest = weekly_digest(uid, target_date)
    logger.info("Weekly digest served user=%s period=%s", uid, digest["period"])
    return jsonify(digest)
