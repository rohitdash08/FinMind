"""Bulk import validation & preview routes."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.services.bulk_import import (
    validate_and_preview,
    execute_import,
    get_import_template,
)

bp = Blueprint("bulk_import", __name__)


@bp.post("/preview")
@jwt_required()
def preview_import():
    """Validate and preview import data before committing.

    Accepts JSON body:
        {
            "content": "<raw CSV or JSON string>",
            "filename": "expenses.csv",   // optional, for format detection
            "format": "csv"               // optional, force format
        }
    """
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or "content" not in data:
        return jsonify({"error": "Missing 'content' field"}), 400

    content = data["content"]
    filename = data.get("filename", "")
    file_format = data.get("format", "")

    result = validate_and_preview(user_id, content, filename, file_format)
    return jsonify(result), 200


@bp.post("/execute")
@jwt_required()
def execute_import_route():
    """Execute the import after user reviews preview.

    Accepts JSON body:
        {
            "content": "<raw CSV or JSON string>",
            "filename": "expenses.csv",
            "format": "csv",
            "skip_invalid": true,
            "create_categories": true
        }
    """
    user_id = int(get_jwt_identity())
    data = request.get_json()

    if not data or "content" not in data:
        return jsonify({"error": "Missing 'content' field"}), 400

    content = data["content"]
    filename = data.get("filename", "")
    file_format = data.get("format", "")
    skip_invalid = data.get("skip_invalid", True)
    create_categories = data.get("create_categories", True)

    result = execute_import(
        user_id=user_id,
        content=content,
        filename=filename,
        file_format=file_format,
        skip_invalid=skip_invalid,
        create_categories=create_categories,
    )
    return jsonify(result), 200


@bp.get("/template")
@jwt_required()
def get_template():
    """Get a sample import template.

    Query params:
        format: "csv" (default) or "json"
    """
    fmt = request.args.get("format", "csv")
    template = get_import_template(fmt)

    content_type = "application/json" if fmt == "json" else "text/csv"
    return template, 200, {"Content-Type": content_type}
