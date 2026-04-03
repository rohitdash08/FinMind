"""Subscription cost monitoring routes.

Provides endpoints for detecting subscription cost increases
and viewing cost trends over time.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.subscription_monitor import detect_cost_increases, get_subscription_trends

bp = Blueprint("subscriptions_monitor", __name__)
logger = logging.getLogger("finmind.subscriptions")


@bp.get("/cost-increases")
@jwt_required()
def list_cost_increases():
    """Return detected subscription cost increases.

    Query params:
        lookback_days (int): How far back to check (default 365, max 730).
        min_change_percent (float): Minimum % to flag (default 0.5).
    """
    uid = int(get_jwt_identity())

    try:
        lookback = min(730, max(30, int(request.args.get("lookback_days", "365"))))
    except (ValueError, TypeError):
        lookback = 365

    try:
        min_pct = max(0.0, float(request.args.get("min_change_percent", "0.5")))
    except (ValueError, TypeError):
        min_pct = 0.5

    changes = detect_cost_increases(uid, lookback_days=lookback, min_change_percent=min_pct)

    logger.info("Cost increase check user=%s results=%s", uid, len(changes))
    return jsonify(changes)


@bp.get("/trends")
@jwt_required()
def subscription_trends():
    """Return cost trend summaries for all recurring subscriptions.

    Query params:
        lookback_days (int): How far back to analyze (default 365).
    """
    uid = int(get_jwt_identity())

    try:
        lookback = min(730, max(30, int(request.args.get("lookback_days", "365"))))
    except (ValueError, TypeError):
        lookback = 365

    trends = get_subscription_trends(uid, lookback_days=lookback)
    return jsonify(trends)
