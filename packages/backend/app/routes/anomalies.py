"""API routes for recurring transaction anomaly alerts (Issue #108)."""

import logging
from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.anomaly_detection import detect_anomalies

bp = Blueprint("anomalies", __name__)
logger = logging.getLogger("finmind.anomalies")


@bp.get("")
@jwt_required()
def list_anomalies():
    """Return detected anomalies for the authenticated user's recurring expenses.

    Query params:
        sensitivity (float): z-score threshold, default 2.0
        since (str): ISO date, only check expenses on/after this date
    """
    uid = int(get_jwt_identity())

    try:
        sensitivity = float(request.args.get("sensitivity", "2.0"))
    except (ValueError, TypeError):
        return jsonify(error="invalid sensitivity value"), 400

    since_raw = request.args.get("since")
    since = None
    if since_raw:
        try:
            since = date.fromisoformat(since_raw)
        except ValueError:
            return jsonify(error="invalid since date, expected YYYY-MM-DD"), 400

    anomalies = detect_anomalies(uid, sensitivity=sensitivity, since=since)
    logger.info("Anomaly scan user=%s found=%s", uid, len(anomalies))

    return jsonify({
        "count": len(anomalies),
        "anomalies": [a.to_dict() for a in anomalies],
    })
