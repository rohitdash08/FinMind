from flask import Blueprint, request, jsonify, g
from ..services.anomaly_engine import AnomalyDetectionEngine
from ..middleware.auth import require_auth

anomaly_bp = Blueprint("anomaly", __name__)
engine = AnomalyDetectionEngine()

@anomaly_bp.route("/api/analytics/anomalies", methods=["GET"])
@require_auth
def detect_anomalies():
    """Detect financial anomalies in recent transactions."""
    user_id = g.user_id
    lookback = int(request.args.get("lookback_days", 90))
    anomalies = engine.detect_anomalies(user_id, lookback_days=lookback)
    return jsonify({
        "anomalies": anomalies,
        "count": len(anomalies),
        "lookback_days": lookback,
    })