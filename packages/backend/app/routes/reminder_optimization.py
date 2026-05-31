from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.reminder_optimizer import (
    get_optimization_insights,
    optimize_reminder_times,
    assign_ab_test_group,
    get_ab_test_results,
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
