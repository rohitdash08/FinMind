import io
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from ..services.import_validation import validate_csv_data, detect_bank_format
import logging

bp = Blueprint("import_validation", __name__)
logger = logging.getLogger("finmind.import_validation")


@bp.post("/validate-csv")
@jwt_required()
def validate_csv():
    file = request.files.get("file")
    if not file:
        return jsonify(error="file required"), 400
    bank_format = request.form.get("bank_format")
    raw = file.read()
    try:
        result = validate_csv_data(raw, bank_format)
    except Exception as exc:
        logger.exception("CSV validation failed")
        return jsonify(error=f"validation failed: {exc}"), 400
    return jsonify(result)


@bp.post("/detect-format")
@jwt_required()
def detect_format():
    file = request.files.get("file")
    if not file:
        return jsonify(error="file required"), 400
    raw = file.read()
    text = raw.decode("utf-8-sig", errors="ignore")
    import csv
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return jsonify(detected_format=None)
    detected = detect_bank_format(reader.fieldnames)
    return jsonify(detected_format=detected)


@bp.get("/formats")
@jwt_required()
def list_formats():
    from ..services.import_validation import CUSTOM_FORMATS
    return jsonify({k: v for k, v in CUSTOM_FORMATS.items()})
