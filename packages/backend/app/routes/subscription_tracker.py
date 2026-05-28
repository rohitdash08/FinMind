"""Subscription Tracker API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.subscription_tracker import SubscriptionTracker

bp = Blueprint("subscription_tracker", __name__)

_services = {}

def _get_service(user_id: str) -> SubscriptionTracker:
    if user_id not in _services:
        _services[user_id] = SubscriptionTracker()
    return _services[user_id]


@bp.post("/")
@jwt_required()
def add_subscription():
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    service = _get_service(user_id)
    return jsonify(service.add(
        user_id=user_id,
        name=data.get("name", ""),
        amount=float(data.get("amount", 0)),
        cycle=data.get("cycle", "monthly"),
        category=data.get("category", "other"),
        start_date=data.get("start_date"),
        is_trial=data.get("is_trial", False),
        trial_end=data.get("trial_end"),
        notes=data.get("notes", ""),
    ))


@bp.get("/")
@jwt_required()
def list_subscriptions():
    user_id = str(get_jwt_identity())
    status = request.args.get("status")
    service = _get_service(user_id)
    return jsonify({"subscriptions": service.get_all(user_id, status)})


@bp.put("/<sub_id>")
@jwt_required()
def update_subscription(sub_id: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.update(sub_id, **data))


@bp.post("/<sub_id>/cancel")
@jwt_required()
def cancel_subscription(sub_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.cancel(sub_id))


@bp.post("/<sub_id>/pause")
@jwt_required()
def pause_subscription(sub_id: str):
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.pause(sub_id))


@bp.post("/<sub_id>/usage")
@jwt_required()
def record_usage(sub_id: str):
    data = request.get_json() or {}
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.record_usage(sub_id, data.get("used", True)))


@bp.get("/summary")
@jwt_required()
def get_summary():
    user_id = str(get_jwt_identity())
    service = _get_service(user_id)
    return jsonify(service.get_summary(user_id))


@bp.get("/upcoming")
@jwt_required()
def get_upcoming():
    user_id = str(get_jwt_identity())
    days = int(request.args.get("days", 30))
    service = _get_service(user_id)
    return jsonify({"upcoming": service.get_upcoming(user_id, days)})
