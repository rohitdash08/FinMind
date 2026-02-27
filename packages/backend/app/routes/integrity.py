"""Financial data integrity & reconciliation API."""

from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.data_integrity import (
    run_all_checks, run_check, reconcile, get_history,
    get_reconciliations, CHECK_TYPES,
)

bp = Blueprint("integrity", __name__)


@bp.get("/check-types")
@jwt_required()
def types():
    return jsonify(CHECK_TYPES)


@bp.post("/check")
@jwt_required()
def check():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    check_type = data.get("check_type")
    if check_type:
        try:
            return jsonify(run_check(uid, check_type))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
    return jsonify(run_all_checks(uid))


@bp.post("/reconcile")
@jwt_required()
def rec():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    try:
        start = date.fromisoformat(data["period_start"])
        end = date.fromisoformat(data["period_end"])
        expected = float(data["expected_total"])
    except (KeyError, ValueError):
        return jsonify({"error": "period_start, period_end, expected_total required"}), 400
    return jsonify(reconcile(uid, start, end, expected)), 201


@bp.get("/history")
@jwt_required()
def history():
    uid = int(get_jwt_identity())
    limit = int(request.args.get("limit", 20))
    return jsonify(get_history(uid, limit))


@bp.get("/reconciliations")
@jwt_required()
def recs():
    uid = int(get_jwt_identity())
    limit = int(request.args.get("limit", 10))
    return jsonify(get_reconciliations(uid, limit))
