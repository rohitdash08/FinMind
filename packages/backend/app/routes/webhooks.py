from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from ..services.webhooks import WebhookService

bp = Blueprint("webhooks", __name__)


@bp.post("/targets")
@jwt_required()
def create_webhook_target():
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    try:
        target = WebhookService.create_target(
            user_id=uid,
            url=str(data.get("url") or "").strip(),
            secret=str(data.get("secret") or ""),
            events=data.get("events"),
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    return jsonify(_target_to_dict(target)), 201


@bp.get("/targets")
@jwt_required()
def get_webhook_targets():
    uid = int(get_jwt_identity())
    targets = WebhookService.get_targets(user_id=uid)
    return jsonify([_target_to_dict(target) for target in targets]), 200


@bp.patch("/targets/<int:target_id>")
@jwt_required()
def update_webhook_target(target_id: int):
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    try:
        target = WebhookService.update_target(
            target_id=target_id,
            user_id=uid,
            url=data.get("url"),
            secret=data.get("secret"),
            events=data.get("events"),
            enabled=data.get("enabled"),
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    if not target:
        return jsonify(error="not found"), 404
    return jsonify(_target_to_dict(target)), 200


@bp.delete("/targets/<int:target_id>")
@jwt_required()
def delete_webhook_target(target_id: int):
    uid = int(get_jwt_identity())
    deleted = WebhookService.delete_target(target_id=target_id, user_id=uid)
    if not deleted:
        return jsonify(error="not found"), 404
    return ("", 204)


@bp.get("/deliveries")
@jwt_required()
def get_webhook_deliveries():
    uid = int(get_jwt_identity())
    target_id = request.args.get("target_id")
    parsed_target_id: int | None = None
    if target_id is not None:
        try:
            parsed_target_id = int(target_id)
        except ValueError:
            return jsonify(error="target_id must be an integer"), 400

    deliveries = WebhookService.get_deliveries(user_id=uid, target_id=parsed_target_id)
    return jsonify([_delivery_to_dict(item) for item in deliveries]), 200


@bp.get("/deliveries/summary")
@jwt_required()
def get_webhook_delivery_summary():
    uid = int(get_jwt_identity())
    target_id = request.args.get("target_id")
    parsed_target_id: int | None = None
    if target_id is not None:
        try:
            parsed_target_id = int(target_id)
        except ValueError:
            return jsonify(error="target_id must be an integer"), 400

    summary = WebhookService.get_delivery_summary(
        user_id=uid, target_id=parsed_target_id
    )
    return jsonify(summary), 200


@bp.post("/deliveries/<int:delivery_id>/redeliver")
@jwt_required()
def redeliver_webhook(delivery_id: int):
    uid = int(get_jwt_identity())
    delivery = WebhookService.redeliver(delivery_id=delivery_id, user_id=uid)
    if not delivery:
        return jsonify(error="not found"), 404
    return jsonify(_delivery_to_dict(delivery)), 200


@bp.post("/process-pending")
@jwt_required()
def process_pending():
    processed = WebhookService.process_pending_deliveries()
    return jsonify(processed=processed), 200


@bp.get("/event-types")
@jwt_required()
def event_types():
    return jsonify(WebhookService.event_types_catalog()), 200


def _target_to_dict(target) -> dict:
    return {
        "id": target.id,
        "url": target.url,
        "events": target.events,
        "enabled": target.enabled,
        "created_at": target.created_at.isoformat(),
        "updated_at": target.updated_at.isoformat(),
    }


def _delivery_to_dict(delivery) -> dict:
    return {
        "id": delivery.id,
        "target_id": delivery.target_id,
        "event_type": delivery.event_type,
        "payload": delivery.payload,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
        "last_attempt_at": (
            delivery.last_attempt_at.isoformat() if delivery.last_attempt_at else None
        ),
        "next_attempt_at": (
            delivery.next_attempt_at.isoformat() if delivery.next_attempt_at else None
        ),
        "response_status": delivery.response_status,
        "response_body": delivery.response_body,
        "created_at": delivery.created_at.isoformat(),
        "updated_at": delivery.updated_at.isoformat(),
    }
