"""PII Export & Delete (GDPR) API Routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.gdpr_pii import gdpr_service

bp = Blueprint("gdpr_pii", __name__)


@bp.post("/export")
@jwt_required()
def export_data():
    """Export all user data (GDPR Article 20 - Right to data portability)."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    user_data = data.get("user_data", {})

    result = gdpr_service.process_export(user_id, user_data)
    return jsonify(result)


@bp.post("/delete")
@jwt_required()
def delete_data():
    """Delete/anonymize user data (GDPR Article 17 - Right to erasure)."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}
    data_collections = data.get("data_collections", {})
    anonymize = data.get("anonymize_instead", True)

    result = gdpr_service.process_deletion(user_id, data_collections, anonymize)
    return jsonify(result)


@bp.post("/verify/<request_id>")
@jwt_required()
def verify_deletion(request_id: str):
    """Verify PII has been properly removed."""
    data = request.get_json() or {}
    current_data = data.get("current_data", {})

    result = gdpr_service.verify_deletion(request_id, current_data)
    return jsonify(result)


@bp.get("/scan")
@jwt_required()
def scan_pii():
    """Scan data for PII fields."""
    from ..services.gdpr_pii import PIIScanner
    data = request.get_json() or {}
    records = data.get("records", [])

    scanner = PIIScanner()
    findings = []
    for record in records:
        findings.extend(scanner.scan_record(record))

    return jsonify({"pii_fields": findings, "count": len(findings)})


@bp.get("/audit-log")
@jwt_required()
def get_audit_log():
    """Get GDPR request audit trail."""
    user_id = str(get_jwt_identity())
    limit = int(request.args.get("limit", 50))

    logs = gdpr_service.get_audit_log(user_id=user_id, limit=limit)
    return jsonify({"audit_log": logs, "count": len(logs)})


@bp.get("/request/<request_id>")
@jwt_required()
def get_request(request_id: str):
    """Get GDPR request status."""
    req = gdpr_service._requests.get(request_id)
    if not req:
        return jsonify({"error": "Request not found"}), 404
    return jsonify(req.to_dict())
