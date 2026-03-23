from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from ..models import User, db
from werkzeug.security import generate_password_hash, check_password_hash

    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        access_token = create_access_token(identity=user.id)
        return jsonify(access_token=access_token), 200
    return jsonify({"msg": "Bad username or password"}), 401