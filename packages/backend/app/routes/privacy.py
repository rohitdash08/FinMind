"""Privacy/GDPR routes for PII export and deletion."""
from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from .services.privacy import export_user_data, delete_user_data
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.get("/export")
@jwt_required()
def export_data():
    """
    Export all user data as a downloadable ZIP file.
    
    Returns a ZIP containing:
    - full_export.json: Complete data export
    - expenses.csv: Expense records
    - bills.csv: Bill records  
    - categories.csv: Category records
    """
    uid = int(get_jwt_identity())
    logger.info("Data export requested by user_id=%s", uid)
    
    buffer, filename = export_user_data(uid)
    
    if not buffer:
        logger.warning("Export failed: user_id=%s not found", uid)
        return jsonify(error="User not found"), 404
    
    logger.info("Data export completed for user_id=%s, file=%s", uid, filename)
    
    return send_file(
        buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=filename
    )


@bp.post("/delete")
@jwt_required()
def request_deletion():
    """
    Request permanent account and data deletion (GDPR right to erasure).
    
    Requires confirmation in request body:
    {
        "confirm": true,
        "confirmation_text": "DELETE MY ACCOUNT"
    }
    
    This action is IRREVERSIBLE.
    """
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    
    # Require explicit confirmation
    confirm = data.get("confirm", False)
    confirmation_text = data.get("confirmation_text", "")
    
    if not confirm or confirmation_text != "DELETE MY ACCOUNT":
        logger.warning(
            "Deletion request rejected for user_id=%s: invalid confirmation", uid
        )
        return jsonify(
            error="Deletion requires confirmation",
            hint='Send {"confirm": true, "confirmation_text": "DELETE MY ACCOUNT"}',
        ), 400
    
    logger.warning("Processing IRREVERSIBLE deletion for user_id=%s", uid)
    
    result = delete_user_data(uid)
    
    if "error" in result:
        logger.error("Deletion failed for user_id=%s: %s", uid, result["error"])
        return jsonify(result), 404
    
    logger.info("Account deletion completed for former user_id=%s", uid)
    
    return jsonify(result), 200


@bp.get("/status")
@jwt_required()
def privacy_status():
    """
    Get privacy status and options for the authenticated user.
    
    Returns information about:
    - Data retention policy
    - Export availability
    - Deletion requirements
    """
    uid = int(get_jwt_identity())
    
    return jsonify({
        "user_id": uid,
        "data_retention_days": 365,
        "export_available": True,
        "deletion_requires_confirmation": True,
        "deletion_is_irreversible": True,
        "gdpr_compliant": True,
        "message": "Your data can be exported or permanently deleted at any time.",
    })
