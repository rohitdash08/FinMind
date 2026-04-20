"""GDPR-compliant PII Export and Delete Workflow API routes."""

import logging
from flask import Blueprint, request, jsonify, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.gdpr import GDPRService


bp = Blueprint("gdpr", __name__)
logger = logging.getLogger("finmind.gdpr")


@bp.route("/gdpr/export", methods=["POST"])
@jwt_required()
def initiate_export():
    """
    Initiate GDPR-compliant data export.
    Returns a signed download token (15-min expiry) for retrieving the export package.
    """
    uid = int(get_jwt_identity())
    try:
        token, download_url = GDPRService.generate_export_package(uid)
        logger.info("GDPR export initiated for user_id=%s", uid)
        return jsonify({
            "message": "Export package generation started",
            "download_token": token,
            "download_url": download_url,
            "expires_in_seconds": 900,
        }), 202
    except Exception as e:
        logger.exception("GDPR export failed for user_id=%s", uid)
        return jsonify(error=str(e)), 500


@bp.route("/gdpr/export/<token>", methods=["GET"])
def download_export(token: str):
    """
    Download the export package using a valid export token.
    Returns JSON or CSV depending on Accept header.
    """
    export_data = GDPRService.get_export_data_by_token(token)
    if not export_data:
        return jsonify(error="Invalid or expired export token"), 404

    accept_header = request.headers.get("Accept", "application/json")
    if "text/csv" in accept_header or request.args.get("format") == "csv":
        csv_packages = GDPRService.export_to_csv(export_data)
        # Return first CSV package as demo; full implementation would zip all
        first_csv = next((v for v in csv_packages.values() if v), "")
        return Response(
            first_csv or "No data",
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=export.csv"}
        )

    return jsonify(export_data)


@bp.route("/gdpr/delete", methods=["POST"])
@jwt_required()
def initiate_deletion():
    """
    Initiate GDPR-compliant user deletion with 30-day grace period.
    Requires email verification to confirm (handled by frontend via /gdpr/delete/confirm).
    """
    uid = int(get_jwt_identity())
    request_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    try:
        confirmation_token = GDPRService.initiate_user_deletion(
            user_id=uid,
            request_ip=request_ip,
            user_agent=user_agent,
        )
        logger.info("GDPR deletion initiated for user_id=%s", uid)
        return jsonify({
            "message": "Deletion initiated. 30-day grace period started.",
            "confirmation_token": confirmation_token,
            "grace_period_days": 30,
        }), 202
    except Exception as e:
        logger.exception("GDPR deletion initiation failed for user_id=%s", uid)
        return jsonify(error=str(e)), 500


@bp.route("/gdpr/delete/<confirmation_token>", methods=["DELETE"])
@jwt_required()
def confirm_deletion(confirmation_token: str):
    """
    Confirm and execute irreversible GDPR user deletion.
    This action is logged and cannot be undone.
    """
    uid = int(get_jwt_identity())
    request_ip = request.remote_addr
    user_agent = request.headers.get("User-Agent")

    # Verify the token belongs to this user
    status = GDPRService.get_deletion_status(confirmation_token)
    if not status:
        return jsonify(error="Invalid or expired deletion token"), 404
    if status["user_id"] != uid:
        return jsonify(error="Token does not belong to this user"), 403

    try:
        success = GDPRService.confirm_user_deletion(
            confirmation_token=confirmation_token,
            request_ip=request_ip,
            user_agent=user_agent,
        )
        if success:
            logger.info("GDPR deletion confirmed and executed for user_id=%s", uid)
            return jsonify({
                "message": "User data permanently deleted. Audit logs retained for 7 years.",
            }), 200
        else:
            return jsonify(error="Deletion failed"), 500
    except Exception as e:
        logger.exception("GDPR deletion confirmation failed for user_id=%s", uid)
        return jsonify(error=str(e)), 500


@bp.route("/gdpr/delete/<confirmation_token>/cancel", methods=["POST"])
@jwt_required()
def cancel_deletion(confirmation_token: str):
    """
    Cancel a pending deletion request during the grace period.
    """
    uid = int(get_jwt_identity())

    status = GDPRService.get_deletion_status(confirmation_token)
    if not status:
        return jsonify(error="Invalid or expired deletion token"), 404
    if status["user_id"] != uid:
        return jsonify(error="Token does not belong to this user"), 403

    try:
        success = GDPRService.cancel_user_deletion(confirmation_token)
        if success:
            logger.info("GDPR deletion cancelled for user_id=%s", uid)
            return jsonify({"message": "Deletion request cancelled."}), 200
        else:
            return jsonify(error="Cancellation failed"), 500
    except Exception as e:
        logger.exception("GDPR deletion cancellation failed for user_id=%s", uid)
        return jsonify(error=str(e)), 500


@bp.route("/gdpr/delete/<confirmation_token>/status", methods=["GET"])
@jwt_required()
def get_deletion_status(confirmation_token: str):
    """
    Get the status of a pending deletion request.
    """
    uid = int(get_jwt_identity())

    status = GDPRService.get_deletion_status(confirmation_token)
    if not status:
        return jsonify(error="Invalid or expired deletion token"), 404
    if status["user_id"] != uid:
        return jsonify(error="Token does not belong to this user"), 403

    return jsonify(status), 200


@bp.route("/gdpr/audit-logs", methods=["GET"])
@jwt_required()
def get_user_audit_logs():
    """
    Retrieve GDPR-related audit logs for the authenticated user.
    Audit logs are retained for 7 years per GDPR compliance.
    """
    uid = int(get_jwt_identity())
    from ..models import AuditLog

    logs = AuditLog.query.filter_by(user_id=uid).order_by(AuditLog.created_at.desc()).limit(100).all()
    return jsonify({
        "audit_logs": [
            {
                "id": log.id,
                "action": log.action,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]
    }), 200
