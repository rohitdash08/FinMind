"""Route: GET /insights/anomalies — Anomaly Detection Engine (#72)."""
from __future__ import annotations

from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.anomaly_detection import detect_anomalies

bp = Blueprint("anomaly_detection", __name__)


@bp.get("/anomalies")
@jwt_required()
def get_anomalies():
    """Return spending anomalies for the authenticated user.

    Query params:
      month (str, optional): YYYY-MM format. Defaults to the current month.

    Returns 200 with:
      {
        "month": "YYYY-MM",
        "anomalies_count": int,
        "has_high_severity": bool,
        "anomalies": [ AnomalyResult, ... ]
      }
    """
    uid = int(get_jwt_identity())
    ym = (request.args.get("month") or date.today().strftime("%Y-%m")).strip()

    result = detect_anomalies(uid, ym)
    return jsonify(result), 200