"""Data Export API for FinMind."""

from flask import Blueprint, jsonify, request, Response
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.data_export import export_csv, export_json, export_ofx, generate_summary_report

bp = Blueprint("data_export", __name__)


@bp.post("/csv")
@jwt_required()
def export_csv_route():
    """Export transactions as CSV."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    filters = data.get("filters", {})

    csv_data = export_csv(transactions, filters)
    return Response(csv_data, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=finmind_export.csv"})


@bp.post("/json")
@jwt_required()
def export_json_route():
    """Export transactions as JSON."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    filters = data.get("filters", {})

    result = export_json(transactions, filters)
    return jsonify(result)


@bp.post("/ofx")
@jwt_required()
def export_ofx_route():
    """Export transactions as OFX."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    filters = data.get("filters", {})
    account_id = data.get("account_id", "finmind-export")

    ofx_data = export_ofx(transactions, filters, account_id)
    return Response(ofx_data, mimetype="application/x-ofx",
                    headers={"Content-Disposition": "attachment; filename=finmind_export.ofx"})


@bp.post("/summary")
@jwt_required()
def export_summary():
    """Generate summary report."""
    data = request.get_json() or {}
    transactions = data.get("transactions", [])
    filters = data.get("filters", {})

    result = generate_summary_report(transactions, filters)
    return jsonify(result)
