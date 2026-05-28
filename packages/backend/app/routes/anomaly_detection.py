"""Anomaly Detection API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.anomaly_detection import AnomalyDetectionService

bp = Blueprint("anomaly_detection", __name__)


@bp.post("/analyze")
@jwt_required()
def full_analysis():
    """Run full anomaly detection."""
    data = request.get_json() or {}
    service = AnomalyDetectionService()
    result = service.full_analysis(
        transactions=data.get("transactions", []),
        user_merchants=set(data.get("known_merchants", [])),
    )
    return jsonify(result)


@bp.post("/outliers")
@jwt_required()
def detect_outliers():
    """Detect amount outliers."""
    data = request.get_json() or {}
    service = AnomalyDetectionService()
    anomalies = service.detect_amount_outliers(data.get("transactions", []))
    return jsonify({"anomalies": [a.to_dict() for a in anomalies]})


@bp.post("/bursts")
@jwt_required()
def detect_bursts():
    """Detect frequency bursts."""
    data = request.get_json() or {}
    service = AnomalyDetectionService()
    anomalies = service.detect_frequency_bursts(data.get("transactions", []))
    return jsonify({"anomalies": [a.to_dict() for a in anomalies]})


@bp.post("/duplicates")
@jwt_required()
def detect_duplicates():
    """Detect potential duplicate transactions."""
    data = request.get_json() or {}
    service = AnomalyDetectionService()
    anomalies = service.detect_duplicates(data.get("transactions", []))
    return jsonify({"anomalies": [a.to_dict() for a in anomalies]})
