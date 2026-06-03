"""
PII Export & Delete Routes (GDPR Article 17 & 20)
"""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.pii_service import export_user_data, delete_user_data
import io

bp = Blueprint("gdpr", __name__)


@bp.route("/export", methods=["POST"])
@jwt_required()
def export_data():
    """
    Export all personal data as a ZIP package (GDPR Article 20).
    
    Returns:
        200: ZIP file download
        404: User not found
        500: Export failed
    """
    user_id = get_jwt_identity()
    
    try:
        zip_data = export_user_data(user_id)
        return send_file(
            io.BytesIO(zip_data),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"finmind_export_user_{user_id}.zip"
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Export failed", "details": str(e)}), 500


@bp.route("/delete", methods=["POST"])
@jwt_required()
def delete_data():
    """
    Permanently delete all user data (GDPR Article 17 - Right to Erasure).
    
    Request body:
        {
            "confirm": true,
            "reason": "optional reason for deletion"
        }
    
    Returns:
        200: Deletion summary
        400: Missing confirmation
        404: User not found
        500: Deletion failed
    """
    user_id = get_jwt_identity()
    data = request.get_json() or {}
    
    if not data.get("confirm"):
        return jsonify({
            "error": "Must set confirm: true to proceed",
            "warning": "This action is IRREVERSIBLE. All your data will be permanently deleted."
        }), 400
    
    reason = data.get("reason", "User requested account deletion")
    
    try:
        summary = delete_user_data(user_id, confirm=True)
        summary["reason"] = reason
        return jsonify({
            "message": "Account and all associated data have been permanently deleted",
            "summary": summary
        }), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": "Deletion failed", "details": str(e)}), 500


@bp.route("/info", methods=["GET"])
@jwt_required()
def data_info():
    """
    Show what personal data we collect (GDPR Article 15 - Right of Access).
    
    Returns:
        200: Data categories and retention info
    """
    return jsonify({
        "data_categories": {
            "profile": {
                "description": "Email, currency preference, account creation date",
                "retention": "Until account deletion",
                "exported": True,
            },
            "expenses": {
                "description": "Expense records with amounts, categories, dates, notes",
                "retention": "Until account deletion",
                "exported": True,
            },
            "recurring_expenses": {
                "description": "Recurring expense templates",
                "retention": "Until account deletion",
                "exported": True,
            },
            "bills": {
                "description": "Bill tracking records",
                "retention": "Until account deletion",
                "exported": True,
            },
            "categories": {
                "description": "Custom expense categories",
                "retention": "Until account deletion",
                "exported": True,
            },
        },
        "your_rights": {
            "access": "POST /api/gdpr/info - View what data we collect",
            "export": "POST /api/gdpr/export - Download all your data",
            "delete": "POST /api/gdpr/delete - Permanently delete your account",
            "rectification": "Contact support to correct inaccurate data",
        },
        "data_controller": "FinMind",
        "contact": "privacy@finmind.app",
    })
