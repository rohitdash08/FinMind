from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services.recurring_anomaly import detect_recurring_anomalies

anomaly_bp = Blueprint("anomaly", __name__, url_prefix="/anomaly")

@anomaly_bp.route("/recurring", methods=["GET"])
@jwt_required()
def recurring_anomalies():
    uid = int(get_jwt_identity())
    months = int(request.args.get("months", 6))
    result = detect_recurring_anomalies(uid, months)
    return jsonify(result), 200
