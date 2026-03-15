"""Universal bank statement normalization routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.bank_statement import (
    normalize_statement,
    detect_statement_format,
    detect_columns,
)

bp = Blueprint("bank_statement", __name__)


@bp.post("/normalize")
@jwt_required()
def normalize_route():
    """Normalize a bank statement into unified transaction schema.

    Accepts JSON body:
        {
            "content": "<raw statement content>",
            "filename": "statement.csv",
            "format": "csv",              // optional
            "column_mapping": {...},       // optional manual mapping
            "date_format": "%d/%m/%Y"     // optional
        }
    """
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Missing 'content' field"}), 400

    result = normalize_statement(
        content=data["content"],
        filename=data.get("filename", ""),
        file_format=data.get("format", ""),
        column_mapping=data.get("column_mapping"),
        date_format=data.get("date_format"),
    )
    return jsonify(result), 200


@bp.post("/detect-format")
@jwt_required()
def detect_format_route():
    """Detect the format of statement content.

    Accepts JSON body:
        {
            "content": "<raw content>",
            "filename": "statement.ofx"
        }
    """
    data = request.get_json()
    if not data or "content" not in data:
        return jsonify({"error": "Missing 'content' field"}), 400

    fmt = detect_statement_format(
        data["content"],
        data.get("filename", ""),
    )
    return jsonify({"format": fmt}), 200


@bp.post("/detect-columns")
@jwt_required()
def detect_columns_route():
    """Auto-detect column mapping from CSV headers.

    Accepts JSON body:
        {
            "headers": ["Date", "Description", "Amount", "Balance"]
        }
    """
    data = request.get_json()
    if not data or "headers" not in data:
        return jsonify({"error": "Missing 'headers' field"}), 400

    mapping = detect_columns(data["headers"])
    return jsonify({"column_mapping": mapping}), 200
