"""Bank statement normalization API."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from ..services.statement_normalizer import normalize_statement
import logging

bp = Blueprint("statements", __name__)
logger = logging.getLogger("finmind.statements")


@bp.post("/normalize")
@jwt_required()
def normalize():
    """Normalize a bank statement. Accepts raw content or file upload."""
    if request.content_type and "multipart" in request.content_type:
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "file is required"}), 400
        content = f.read().decode("utf-8", errors="replace")
        hint = request.form.get("format")
    else:
        data = request.get_json()
        if not data or not data.get("content"):
            return jsonify({"error": "content is required"}), 400
        content = data["content"]
        hint = data.get("format")

    result = normalize_statement(content, hint)
    logger.info("Statement normalized format=%s txns=%s", result["format_detected"], result["total_transactions"])
    return jsonify(result)


@bp.post("/preview")
@jwt_required()
def preview():
    """Preview first 5 normalized transactions without full processing."""
    data = request.get_json()
    if not data or not data.get("content"):
        return jsonify({"error": "content is required"}), 400

    result = normalize_statement(data["content"], data.get("format"))
    result["transactions"] = result["transactions"][:5]
    result["preview"] = True
    return jsonify(result)
