from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User

bp = Blueprint("household", __name__, url_prefix="/api/household")


@bp.route("", methods=["POST"])
@jwt_required()
def create_household():
    uid = get_jwt_identity()
    data = request.get_json() or {}
    name = data.get("name")
    
    if not name:
        return jsonify(error="name required"), 400
    
    # Create household (simplified - just a name associated with users)
    # In production, would have a separate household table
    return jsonify(
        id=uid,
        name=name,
        owner_id=int(uid),
        members=[int(uid)]
    ), 201


@bp.route("", methods=["GET"])
@jwt_required()
def get_household():
    uid = get_jwt_identity()
    # Simplified - return demo household
    return jsonify(
        id=1,
        name="My Household",
        owner_id=int(uid),
        members=[int(uid)]
    )


@bp.route("/members", methods=["POST"])
@jwt_required()
def add_member():
    uid = get_jwt_identity()
    data = request.get_json() or {}
    email = data.get("email")
    
    if not email:
        return jsonify(error="email required"), 400
    
    # Find user by email
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify(error="user not found"), 404
    
    return jsonify(
        message="member added",
        user_id=user.id,
        email=user.email
    )
