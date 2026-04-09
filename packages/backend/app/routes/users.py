import logging
from flask import Blueprint, jsonify, request, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.user_data import export_user_data, delete_user_data

bp = Blueprint("users", __name__)
logger = logging.getLogger("finmind.users")


@bp.get("/me/export")
@jwt_required()
def export_my_data():
    """
    Exports all personal data associated with the authenticated user.
    """
    user_id = int(get_jwt_identity())
    data = export_user_data(user_id)
    if not data:
        return jsonify({"message": "User not found or no data to export"}), 404

    logger.info("User data exported for user_id=%s", user_id)
    return jsonify(data), 200


@bp.delete("/me")
@jwt_required()
def delete_my_data():
    """
    Permanently deletes the authenticated user's account and all associated data.
    Requires explicit confirmation via JSON body.
    """
    user_id = int(get_jwt_identity())
    
    # Require explicit confirmation for irreversible deletion
    confirmation = request.get_json(silent=True)
    if not confirmation or not confirmation.get("confirm", False) is True:
        logger.warning("Account deletion attempted without confirmation for user_id=%s", user_id)
        abort(400, description="Account deletion requires explicit confirmation: {'confirm': true}")

    if delete_user_data(user_id):
        logger.info("User account and all associated data permanently deleted for user_id=%s", user_id)
        return jsonify({"message": "Account and all associated data permanently deleted"}), 200
    else:
        logger.error("Failed to delete user account for user_id=%s", user_id)
        return jsonify({"message": "Failed to delete account"}), 500
