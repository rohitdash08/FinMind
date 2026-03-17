from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.models import User, db, AuditLog
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
import datetime
    return jsonify({"msg": "Bad username or password"}), 401

@auth.route('/export-data', methods=['GET'])
@jwt_required()
def export_data():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # Export user data
    user_data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "expenses": [expense.to_dict() for expense in user.expenses],
        "bills": [bill.to_dict() for bill in user.bills],
        "reminders": [reminder.to_dict() for reminder in user.reminders]
    }

    # Log audit trail
    audit_log = AuditLog(user_id=user_id, action="export_data")
    db.session.add(audit_log)
    db.session.commit()

    return jsonify(user_data), 200


@auth.route('/delete-data', methods=['DELETE'])
@jwt_required()
def delete_data():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"msg": "User not found"}), 404

    # Delete user data
    db.session.delete(user)
    db.session.commit()

    # Log audit trail
    audit_log = AuditLog(user_id=user_id, action="delete_data")
    db.session.add(audit_log)
    db.session.commit()

    return jsonify({"msg": "Data deleted successfully"}), 200
