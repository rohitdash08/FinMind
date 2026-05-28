"""Data Integrity & Reconciliation API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.data_integrity import DataIntegrityService

bp = Blueprint("data_integrity", __name__)


@bp.post("/checksum")
@jwt_required()
def compute_checksum():
    """Compute integrity checksum for a record."""
    data = request.get_json() or {}
    record = data.get("record", {})
    service = DataIntegrityService()
    checksum = service.compute_checksum(record)
    return jsonify({"checksum": checksum})


@bp.post("/verify")
@jwt_required()
def verify_checksum():
    """Verify a record's checksum."""
    data = request.get_json() or {}
    record = data.get("record", {})
    expected = data.get("expected_checksum", "")
    service = DataIntegrityService()
    valid = service.verify_checksum(record, expected)
    return jsonify({"valid": valid})


@bp.post("/audit")
@jwt_required()
def run_audit():
    """Run full data integrity audit."""
    user_id = str(get_jwt_identity())
    data = request.get_json() or {}

    service = DataIntegrityService()
    report = service.run_full_audit(
        user_id=user_id,
        transactions=data.get("transactions", []),
        accounts=data.get("accounts", []),
        categories=data.get("categories", []),
        stated_balance=float(data.get("stated_balance", 0)),
        starting_balance=float(data.get("starting_balance", 0)),
    )

    return jsonify(report.to_dict())


@bp.post("/check-duplicates")
@jwt_required()
def check_duplicates():
    """Check for duplicate transactions."""
    data = request.get_json() or {}
    service = DataIntegrityService()
    duplicates = service.check_duplicates(data.get("transactions", []))
    return jsonify({"duplicates": duplicates, "count": len(duplicates)})


@bp.post("/reconcile")
@jwt_required()
def reconcile():
    """Reconcile transactions against stated balance."""
    data = request.get_json() or {}
    service = DataIntegrityService()
    result = service.check_balance_reconciliation(
        transactions=data.get("transactions", []),
        stated_balance=float(data.get("stated_balance", 0)),
        starting_balance=float(data.get("starting_balance", 0)),
    )
    return jsonify(result)
