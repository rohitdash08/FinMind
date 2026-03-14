"""Weekly financial digest API routes."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.digest import generate_weekly_digest, save_digest, get_digest_history

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Generate (or regenerate) the weekly digest for a given week.

    Query params:
      - week: ISO date (YYYY-MM-DD) falling within the desired week.
              Defaults to today (current week).
    """
    uid = int(get_jwt_identity())
    raw_date = (request.args.get("week") or "").strip()
    ref_date = None
    if raw_date:
        try:
            ref_date = date.fromisoformat(raw_date)
        except ValueError:
            return jsonify(error="invalid week parameter, expected YYYY-MM-DD"), 400

    summary = generate_weekly_digest(uid, ref_date)
    digest = save_digest(uid, summary)
    logger.info(
        "Weekly digest generated user=%s week=%s", uid, summary["period"]["week_start"]
    )
    return jsonify(
        {
            "id": digest.id,
            "week_start": digest.week_start.isoformat(),
            "week_end": digest.week_end.isoformat(),
            "generated_at": digest.generated_at.isoformat()
            if digest.generated_at
            else None,
            "summary": summary,
        }
    )


@bp.get("/history")
@jwt_required()
def digest_history():
    """List past weekly digests for the authenticated user.

    Query params:
      - limit: max number of digests to return (default 12, max 52).
    """
    uid = int(get_jwt_identity())
    try:
        limit = min(52, max(1, int(request.args.get("limit", "12"))))
    except ValueError:
        limit = 12

    history = get_digest_history(uid, limit=limit)
    logger.info("Digest history served user=%s count=%s", uid, len(history))
    return jsonify(history)
