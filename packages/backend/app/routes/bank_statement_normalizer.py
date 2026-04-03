"""
Bank Statement Normalization Route (#112)
"""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import logging

from ..services.bank_statement_normalizer import normalize_statement_to_dict

bp = Blueprint("bank_statement_normalizer", __name__)
logger = logging.getLogger("finmind.bank_statement_normalizer")


@bp.post("/normalize-statement")
@jwt_required()
def normalize_statement():
    """
    Normalize a bank statement CSV/TSV into unified schema.

    Request Body (JSON):
        content (str): Raw CSV/TSV content of the bank statement
        format (str): 'csv', 'tsv', or 'auto' (default: 'auto')

    Returns:
        Normalized transactions in unified schema
    """
    uid = int(get_jwt_identity())
    data = request.get_json(silent=True) or {}

    content = data.get("content", "")
    file_format = data.get("format", "auto")

    if not content:
        return jsonify({"error": "content is required"}), 400

    if file_format not in ("csv", "tsv", "auto"):
        file_format = "auto"

    result = normalize_statement_to_dict(content, file_format)
    logger.info(
        "Statement normalized user=%s parsed=%d skipped=%d",
        uid, result["parsed_rows"], result["skipped_rows"],
    )
    return jsonify(result)


@bp.get("/normalize-statement/sample")
def get_sample_formats():
    """
    Get sample bank statement formats that are supported.
    No auth needed - helps frontend with format documentation.
    """
    return jsonify({
        "supported_formats": ["csv", "tsv"],
        "auto_detection": True,
        "supported_column_headers": {
            "date": ["date", "transaction date", "txn date", "posting date", "value date"],
            "description": ["description", "narration", "particulars", "details", "memo"],
            "amount": ["amount", "transaction amount"],
            "debit_credit_split": ["debit/withdrawal + credit/deposit columns"],
            "balance": ["balance", "running balance"],
            "reference": ["reference", "ref", "transaction id"],
        },
        "supported_date_formats": [
            "DD/MM/YYYY", "DD-MM-YYYY", "MM/DD/YYYY",
            "YYYY-MM-DD", "DD Mon YYYY", "Mon DD, YYYY",
        ],
        "amount_formats": [
            "1234.56", "1,234.56", "1.234,56 (European)",
            "(1234.56) for negatives", "1234.56CR/DR suffixes",
        ],
    })
