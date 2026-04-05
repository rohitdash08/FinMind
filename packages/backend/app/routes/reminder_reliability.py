from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.reminder_reliability import record_acknowledged, get_metrics, get_status

bp = Blueprint("reminder_metrics", __name__)

@bp.get("/metrics")
@jwt_required()
def metrics():
    return jsonify(get_metrics())

@bp.post("/<int:reminder_id>/ack")
@jwt_required()
def ack(reminder_id):
    record_acknowledged(reminder_id)
    return jsonify({"acknowledged": True})

@bp.get("/<int:reminder_id>/status")
@jwt_required()
def status(reminder_id):
    s = get_status(reminder_id)
    return jsonify(s) if s else (jsonify(error="not found"), 404)
