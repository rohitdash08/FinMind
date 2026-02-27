"""Event-driven financial activity system API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.event_system import (
    publish, get_events, subscribe, get_subscriptions,
    unsubscribe, get_event_types,
)

bp = Blueprint("events", __name__)


@bp.get("/types")
@jwt_required()
def types():
    return jsonify(get_event_types())


@bp.post("/publish")
@jwt_required()
def pub():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("event_type"):
        return jsonify({"error": "event_type is required"}), 400
    try:
        result = publish(uid, data["event_type"], data.get("payload"), data.get("source", "user"))
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/")
@jwt_required()
def list_events():
    uid = int(get_jwt_identity())
    event_type = request.args.get("type")
    limit = int(request.args.get("limit", 50))
    return jsonify(get_events(uid, event_type, limit))


@bp.post("/subscriptions")
@jwt_required()
def sub():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    if not data.get("event_type"):
        return jsonify({"error": "event_type is required"}), 400
    try:
        result = subscribe(uid, data["event_type"], data.get("webhook_url"))
        return jsonify(result), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@bp.get("/subscriptions")
@jwt_required()
def list_subs():
    uid = int(get_jwt_identity())
    return jsonify(get_subscriptions(uid))


@bp.delete("/subscriptions/<int:sub_id>")
@jwt_required()
def unsub(sub_id):
    uid = int(get_jwt_identity())
    if unsubscribe(uid, sub_id):
        return jsonify({"message": "Unsubscribed"})
    return jsonify({"error": "Subscription not found"}), 404
