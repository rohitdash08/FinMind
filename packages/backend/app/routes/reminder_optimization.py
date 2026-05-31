from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.reminder_optimizer import (
    get_optimization_insights,
    optimize_reminder_times,
    assign_ab_test_group,
    get_ab_test_results,
    record_performance_metric,
    get_performance_dashboard,
    record_engagement,
)
import logging

bp = Blueprint("reminder_optimization", __name__)
logger = logging.getLogger("finmind.reminder_optimization")


@bp.get("/insights")
@jwt_required()
def insights():
    uid = int(get_jwt_identity())
    data = get_optimization_insights(uid)
    return jsonify(data)


@bp.post("/apply")
@jwt_required()
def apply():
    uid = int(get_jwt_identity())
    count = optimize_reminder_times(uid)
    return jsonify(updated=count)


@bp.post("/ab-test/assign")
@jwt_required()
def assign_ab():
    uid = int(get_jwt_identity())
    variant = assign_ab_test_group(uid)
    return jsonify(variant=variant)


@bp.get("/ab-test/results")
@jwt_required()
def ab_results():
    uid = int(get_jwt_identity())
    results = get_ab_test_results(uid)
    return jsonify(results)


@bp.post("/record-engagement")
@jwt_required()
def record():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    event_type = data.get("event_type", "opened")
    channel = data.get("channel", "email")
    record_engagement(uid, event_type, channel)
    return jsonify(message="recorded"), 201


@bp.post("/metrics")
@jwt_required()
def record_metric():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    metric_type = data.get("metric_type")
    metric_value = data.get("metric_value")
    channel = data.get("channel")
    if not metric_type or metric_value is None:
        return jsonify(error="metric_type and metric_value required"), 400
    record_performance_metric(uid, metric_type, float(metric_value), channel)
    return jsonify(message="recorded"), 201


@bp.get("/dashboard")
@jwt_required()
def dashboard():
    uid = int(get_jwt_identity())
    data = get_performance_dashboard(uid)
    return jsonify(data)
