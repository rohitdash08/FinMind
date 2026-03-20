from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.bank_normalization import normalize_bank_statement

bp = Blueprint("bank_normalization", __name__)


@bp.route("/normalize-statement", methods=["POST"])
@jwt_required()
def normalize_statement():
    """
    POST /insights/normalize-statement

    Normalize diverse bank statement formats into a unified transaction schema.

    Request body (JSON):
        rows: list[dict]         — raw statement rows (required)
        date_field: str          — name of the date column (default: "date")
        description_field: str   — name of description column (default: "description")
        amount_field: str        — name of amount column (default: "amount")
        type_field: str          — optional column for transaction type
        debit_field: str         — optional separate debit column
        credit_field: str        — optional separate credit column
        currency: str            — default currency (default: "USD")
    """
    data = request.get_json(silent=True) or {}

    rows = data.get("rows", [])
    if not isinstance(rows, list):
        return jsonify({"error": "rows must be a list of objects"}), 400

    result = normalize_bank_statement(
        rows=rows,
        date_field=data.get("date_field", "date"),
        description_field=data.get("description_field", "description"),
        amount_field=data.get("amount_field", "amount"),
        type_field=data.get("type_field"),
        debit_field=data.get("debit_field"),
        credit_field=data.get("credit_field"),
        currency=data.get("currency", "USD"),
    )

    return jsonify(
        {
            "total_rows": result.total_rows,
            "success_count": result.success_count,
            "rejection_count": result.rejection_count,
            "detected_format": result.detected_format,
            "summary": result.summary,
            "normalized": [
                {
                    "date": n.date,
                    "description": n.description,
                    "amount": n.amount,
                    "type": n.type,
                    "currency": n.currency,
                    "category_hint": n.category_hint,
                }
                for n in result.normalized
            ],
            "rejected": [
                {"row": r["row"], "reason": r["reason"]}
                for r in result.rejected
            ],
        }
    )