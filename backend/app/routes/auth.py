from flask import Blueprint, request, jsonify
from flask_webhook import emit_event
from backend.app.models import User, db
from flask_jwt_extended import create_access_token, create_refresh_token, jwt_required, get_jwt_identity

    db.session.commit()
    return jsonify(user.to_dict()), 201
    emit_event('user_created', user)

@bp.route('/auth/login', methods=['POST'])
def login():