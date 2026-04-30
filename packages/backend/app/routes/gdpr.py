"""GDPR privacy routes — data export & account deletion."""

import json
from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.gdpr import (
    confirm_data_deletion,
    generate_export_package,
    get_request_status,
    get_user_requests,
    request_data_deletion,
    request_data_export,
)
from ..models import DataRequest, DataRequestStatus, DataRequestType
from ..extensions import db
from datetime import datetime
import logging

bp = Blueprint("privacy", __name__)
logger = logging.getLogger("finmind.privacy")


@bp.post("/export")
@jwt_required()
def create_export():
    """Request a data export package."""
    uid = int(get_jwt_identity())
    try:
        req = request_data_export(uid)
        logger.info("Export request created user_id=%s request_id=%s", uid, req.id)
        return jsonify(
            request_id=req.id,
            status=req.status,
            message="Export ready for download",
        ), 201
    except Exception as exc:
        logger.exception("Export request failed user_id=%s", uid)
        return jsonify(error=f"Export failed: {exc}"), 500


@bp.get("/export/<int:request_id>")
@jwt_required()
def download_export(request_id: int):
    """Download a completed export package as JSON."""
    uid = int(get_jwt_identity())
    req = db.session.get(DataRequest, request_id)

    if not req or req.user_id != uid:
        return jsonify(error="not found"), 404

    if req.request_type != DataRequestType.EXPORT.value:
        return jsonify(error="not an export request"), 400

    if req.status != DataRequestStatus.COMPLETED.value:
        return jsonify(error="export not ready", status=req.status), 400

    # Check expiry
    if req.expires_at and datetime.utcnow() > req.expires_at:
        return jsonify(error="export has expired, please request a new one"), 410

    # Regenerate the export package (stateless approach)
    try:
        export_data = generate_export_package(uid)
    except ValueError:
        return jsonify(error="user not found"), 404

    export_json = json.dumps(export_data, ensure_ascii=False, default=str, indent=2)

    return Response(
        export_json,
        mimetype="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=finmind-export-{uid}.json",
        },
    )


@bp.get("/requests")
@jwt_required()
def list_requests():
    """List past data requests for the current user."""
    uid = int(get_jwt_identity())
    requests_list = get_user_requests(uid)
    return jsonify(requests_list)


@bp.post("/delete")
@jwt_required()
def create_deletion():
    """Request account deletion. Returns a confirmation token."""
    uid = int(get_jwt_identity())
    try:
        result = request_data_deletion(uid)
        logger.info("Deletion request created user_id=%s request_id=%s", uid, result["request_id"])
        return jsonify(
            request_id=result["request_id"],
            confirmation_token=result["confirmation_token"],
            message="Please confirm deletion by sending the confirmation token to POST /privacy/delete/confirm",
        ), 201
    except Exception as exc:
        logger.exception("Deletion request failed user_id=%s", uid)
        return jsonify(error=f"Deletion request failed: {exc}"), 500


@bp.post("/delete/confirm")
@jwt_required()
def confirm_deletion():
    """Confirm and execute account deletion with confirmation token."""
    uid = int(get_jwt_identity())
    data = request.get_json() or {}

    request_id = data.get("request_id")
    confirmation_token = data.get("confirmation_token")

    if not request_id or not confirmation_token:
        return jsonify(error="request_id and confirmation_token required"), 400

    try:
        req = confirm_data_deletion(uid, int(request_id), confirmation_token)
        logger.info("Deletion confirmed user_id=%s request_id=%s", uid, request_id)
        return jsonify(
            request_id=req.id,
            status=req.status,
            message="Account and all associated data have been permanently deleted",
        )
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    except Exception as exc:
        logger.exception("Deletion confirmation failed user_id=%s", uid)
        return jsonify(error=f"Deletion failed: {exc}"), 500
