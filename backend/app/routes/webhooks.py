from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, webhook_logger
from app.models import User, WebhookEndpoint, WebhookDeliveryAttempt
import secrets # For generating secure secrets

webhooks_bp = Blueprint('webhooks', __name__)

@webhooks_bp.route('/endpoints', methods=['POST'])
@jwt_required()
def create_webhook_endpoint():
    """Create a new webhook endpoint for the authenticated user."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    data = request.get_json()
    url = data.get('url')
    event_types = data.get('event_types', [])

    if not url:
        return jsonify({"message": "Webhook URL is required"}), 400
    if not isinstance(event_types, list):
        return jsonify({"message": "event_types must be a list of strings"}), 400
    if not all(isinstance(et, str) for et in event_types):
        return jsonify({"message": "All event_types must be strings"}), 400

    # Generate a secure secret for signing
    webhook_secret = secrets.token_hex(32) # 64-character hex string

    new_endpoint = WebhookEndpoint(
        user_id=user.id,
        url=url,
        secret=webhook_secret,
        event_types=event_types,
        is_active=True
    )
    db.session.add(new_endpoint)
    db.session.commit()

    # Return the secret ONLY once upon creation
    response_data = new_endpoint.to_dict()
    response_data['secret'] = webhook_secret
    
    webhook_logger.info(f"User {user.id} created new webhook endpoint {new_endpoint.id} for URL: {url}")
    return jsonify(response_data), 201

@webhooks_bp.route('/endpoints', methods=['GET'])
@jwt_required()
def list_webhook_endpoints():
    """List all webhook endpoints for the authenticated user."""
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    endpoints = WebhookEndpoint.query.filter_by(user_id=user.id).all()
    return jsonify([endpoint.to_dict() for endpoint in endpoints]), 200

@webhooks_bp.route('/endpoints/<int:endpoint_id>', methods=['GET'])
@jwt_required()
def get_webhook_endpoint(endpoint_id):
    """Get a specific webhook endpoint by ID for the authenticated user."""
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify({"message": "Webhook endpoint not found or unauthorized"}), 404
    return jsonify(endpoint.to_dict()), 200

@webhooks_bp.route('/endpoints/<int:endpoint_id>', methods=['PUT'])
@jwt_required()
def update_webhook_endpoint(endpoint_id):
    """Update an existing webhook endpoint for the authenticated user."""
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify({"message": "Webhook endpoint not found or unauthorized"}), 404

    data = request.get_json()
    endpoint.url = data.get('url', endpoint.url)
    endpoint.event_types = data.get('event_types', endpoint.event_types)
    endpoint.is_active = data.get('is_active', endpoint.is_active)

    if not isinstance(endpoint.event_types, list):
        return jsonify({"message": "event_types must be a list of strings"}), 400
    if not all(isinstance(et, str) for et in endpoint.event_types):
        return jsonify({"message": "All event_types must be strings"}), 400
    
    db.session.commit()
    webhook_logger.info(f"User {user_id} updated webhook endpoint {endpoint.id}. URL: {endpoint.url}, Active: {endpoint.is_active}")
    return jsonify(endpoint.to_dict()), 200

@webhooks_bp.route('/endpoints/<int:endpoint_id>/rotate-secret', methods=['POST'])
@jwt_required()
def rotate_webhook_secret(endpoint_id):
    """Rotate the secret for a webhook endpoint."""
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify({"message": "Webhook endpoint not found or unauthorized"}), 404

    new_secret = secrets.token_hex(32)
    endpoint.secret = new_secret
    db.session.commit()
    
    response_data = endpoint.to_dict()
    response_data['secret'] = new_secret # Return new secret
    webhook_logger.info(f"User {user_id} rotated secret for webhook endpoint {endpoint.id}.")
    return jsonify(response_data), 200

@webhooks_bp.route('/endpoints/<int:endpoint_id>', methods=['DELETE'])
@jwt_required()
def delete_webhook_endpoint(endpoint_id):
    """Delete a webhook endpoint for the authenticated user."""
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify({"message": "Webhook endpoint not found or unauthorized"}), 404

    db.session.delete(endpoint)
    db.session.commit()
    webhook_logger.info(f"User {user_id} deleted webhook endpoint {endpoint.id}.")
    return jsonify({"message": "Webhook endpoint deleted"}), 204

@webhooks_bp.route('/endpoints/<int:endpoint_id>/delivery-attempts', methods=['GET'])
@jwt_required()
def list_delivery_attempts(endpoint_id):
    """List delivery attempts for a specific webhook endpoint."""
    user_id = get_jwt_identity()
    endpoint = WebhookEndpoint.query.filter_by(id=endpoint_id, user_id=user_id).first()
    if not endpoint:
        return jsonify({"message": "Webhook endpoint not found or unauthorized"}), 404

    attempts = WebhookDeliveryAttempt.query.filter_by(endpoint_id=endpoint.id).order_by(WebhookDeliveryAttempt.created_at.desc()).limit(20).all()
    return jsonify([attempt.to_dict() for attempt in attempts]), 200

