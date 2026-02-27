"""Weekly digest API endpoints."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly-digest")
@jwt_required()
def get_weekly_digest():
    """Return the weekly financial digest for the authenticated user.

    Query params:
        date (optional): ISO date (YYYY-MM-DD) to anchor the week. Defaults to today.
    """
    uid = int(get_jwt_identity())
    ref = request.args.get("date")
    ref_date = date.fromisoformat(ref) if ref else None
    digest = weekly_digest(uid, ref_date)
    logger.info("Weekly digest served user=%s week=%s", uid, digest["week"]["start"])
    return jsonify(digest)
