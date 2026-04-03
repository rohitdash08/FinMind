"""Recurring transaction anomaly detection routes.

Provides endpoints for users to check for anomalies in their
recurring expenses and transaction patterns.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.anomaly_detection import detect_anomalies

bp = Blueprint("anomalies", __name__)
logger = logging.getLogger("finmind.anomalies")


@bp.get("")
@jwt_required()
def list_anomalies():
    """Return detected anomalies for the authenticated user.

    Query params:
        lookback_days (int): How far back to analyze (default 90, max 365).
        severity (str): Filter by severity — low, medium, high (optional).
        type (str): Filter by anomaly type (optional).

    Returns:
        JSON array of anomaly objects.
    """
    uid = int(get_jwt_identity())

    try:
        lookback = min(365, max(7, int(request.args.get("lookback_days", "90"))))
    except (ValueError, TypeError):
        lookback = 90

    severity_filter = request.args.get("severity", "").lower().strip() or None
    type_filter = request.args.get("type", "").strip() or None

    anomalies = detect_anomalies(uid, lookback_days=lookback)

    if severity_filter:
        anomalies = [a for a in anomalies if a["severity"] == severity_filter]
    if type_filter:
        anomalies = [a for a in anomalies if a["type"] == type_filter]

    logger.info(
        "Anomaly check user=%s lookback=%s results=%s", uid, lookback, len(anomalies)
    )
    return jsonify(anomalies)


@bp.get("/summary")
@jwt_required()
def anomaly_summary():
    """Return a summary count of anomalies grouped by type and severity."""
    uid = int(get_jwt_identity())

    try:
        lookback = min(365, max(7, int(request.args.get("lookback_days", "90"))))
    except (ValueError, TypeError):
        lookback = 90

    anomalies = detect_anomalies(uid, lookback_days=lookback)

    by_type: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for a in anomalies:
        by_type[a["type"]] = by_type.get(a["type"], 0) + 1
        by_severity[a["severity"]] = by_severity.get(a["severity"], 0) + 1

    return jsonify(
        {
            "total": len(anomalies),
            "by_type": by_type,
            "by_severity": by_severity,
        }
    )
