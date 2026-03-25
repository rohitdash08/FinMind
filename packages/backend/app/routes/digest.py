"""Weekly digest endpoints."""

import json
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..models import WeeklyDigest
from ..services.digest import generate_digest

bp = Blueprint("digest", __name__)


@bp.get("/latest")
@jwt_required()
def get_latest_digest():
    """Get the most recent weekly digest for the current user."""
    user_id = int(get_jwt_identity())
    digest = (
        WeeklyDigest.query.filter_by(user_id=user_id)
        .order_by(WeeklyDigest.week_start.desc())
        .first()
    )
    if not digest:
        return jsonify(error="No digest available yet"), 404
    return jsonify(_serialize(digest)), 200


@bp.get("/history")
@jwt_required()
def get_digest_history():
    """Get digest history for the current user."""
    user_id = int(get_jwt_identity())
    limit = request.args.get("limit", 10, type=int)
    limit = max(1, min(limit, 52))

    digests = (
        WeeklyDigest.query.filter_by(user_id=user_id)
        .order_by(WeeklyDigest.week_start.desc())
        .limit(limit)
        .all()
    )
    return jsonify([_serialize(d) for d in digests]), 200


@bp.post("/generate")
@jwt_required()
def trigger_digest():
    """Manually trigger digest generation for the current user."""
    user_id = int(get_jwt_identity())
    digest = generate_digest(user_id)
    if not digest:
        return jsonify(error="No transactions found for last week"), 404
    return jsonify(_serialize(digest)), 201


def _serialize(digest):
    return {
        "id": digest.id,
        "week_start": digest.week_start.isoformat(),
        "week_end": digest.week_end.isoformat(),
        "summary": digest.summary,
        "tips": json.loads(digest.tips),
        "highlights": json.loads(digest.highlights),
        "method": digest.method,
        "created_at": digest.created_at.isoformat(),
    }
