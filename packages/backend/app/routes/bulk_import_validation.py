from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.bulk_import_validation import validate_bulk_import

bp = Blueprint("bulk_import_validation", __name__)


@bp.route("/import-preview", methods=["POST"])
@jwt_required()
def import_preview():
    """
    POST /insights/import-preview

    Validate and preview bulk transaction import before committing.
    Returns per-row validation results with warnings and auto-corrections.

    Request body:
        rows: list[dict]         — raw transaction rows
        date_field: str          — (optional) date column name, default "date"
        amount_field: str        — (optional) amount column name, default "amount"
        description_field: str   — (optional) description column, default "description"
        strict: bool             — (optional) fail on zero amounts, default false
    """
    data = request.get_json(silent=True) or {}
    rows = data.get("rows", [])
    if not isinstance(rows, list):
        return jsonify({"error": "rows must be a list"}), 400

    result = validate_bulk_import(
        rows=rows,
        date_field=data.get("date_field", "date"),
        amount_field=data.get("amount_field", "amount"),
        description_field=data.get("description_field", "description"),
        strict=bool(data.get("strict", False)),
    )

    return jsonify(
        {
            "total_rows": result.total_rows,
            "valid_rows": result.valid_rows,
            "warning_rows": result.warning_rows,
            "invalid_rows": result.invalid_rows,
            "ready_to_import": result.ready_to_import,
            "schema_detected": result.schema_detected,
            "summary": result.summary,
            "validations": [
                {
                    "row_index": v.row_index,
                    "is_valid": v.is_valid,
                    "warnings": v.warnings,
                    "corrections": v.corrections,
                }
                for v in result.validations
            ],
            "corrected_preview": result.corrected_preview,
        }
    )