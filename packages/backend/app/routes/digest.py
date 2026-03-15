"""Smart weekly financial digest endpoints.

Endpoints
---------
GET  /digest/weekly          – Generate current week's digest
GET  /digest/weekly/history  – List digest metadata for past weeks
"""

from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.digest import generate_weekly_digest

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Return the smart weekly digest for the authenticated user.

    Query params:
        date (str, optional): Anchor date (YYYY-MM-DD). Defaults to today.
    """
    uid = int(get_jwt_identity())
    anchor_str = request.args.get("date")

    anchor = None
    if anchor_str:
        try:
            anchor = date.fromisoformat(anchor_str)
        except ValueError:
            return jsonify(error="invalid date, expected YYYY-MM-DD"), 400

    digest = generate_weekly_digest(uid, anchor)
    logger.info("Weekly digest served user=%s period=%s..%s",
                uid, digest["period"]["start"], digest["period"]["end"])
    return jsonify(digest=digest), 200


@bp.get("/weekly/history")
@jwt_required()
def weekly_history():
    """Return metadata for the last N weeks to populate a digest history view.

    Query params:
        weeks (int, optional): Number of past weeks to include. Default 4.
    """
    uid = int(get_jwt_identity())
    weeks = min(request.args.get("weeks", 4, type=int), 12)
    today = date.today()

    history = []
    for i in range(weeks):
        anchor = today - timedelta(weeks=i)
        digest = generate_weekly_digest(uid, anchor)
        history.append({
            "period": digest["period"],
            "summary": digest["summary"],
            "insight_count": len(digest["insights"]),
        })

    return jsonify(history=history), 200
