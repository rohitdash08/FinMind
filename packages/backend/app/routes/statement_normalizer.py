from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.statement_normalizer import (
    get_adapters,
    register_adapter,
    preview_normalization,
    commit_normalization,
)
import logging

bp = Blueprint("statement_normalizer", __name__)
logger = logging.getLogger("finmind.statement_normalizer")


@bp.get("/adapters")
@jwt_required()
def list_adapters():
    adapters = get_adapters()
    return jsonify(adapters)


@bp.post("/adapters")
@jwt_required()
def register_new_adapter():
    data = request.get_json() or {}
    if not data.get("name") or not data.get("format") or not data.get("schema_map"):
        return jsonify(error="name, format, and schema_map required"), 400
    adapter = register_adapter(data)
    return jsonify(adapter), 201


@bp.post("/preview")
@jwt_required()
def preview():
    uid = int(get_jwt_identity())
    file = request.files.get("file")
    if not file:
        return jsonify(error="file required"), 400
    adapter_name = request.form.get("adapter")
    try:
        result = preview_normalization(
            user_id=uid,
            filename=file.filename or "",
            content=file.read(),
            adapter_name=adapter_name,
        )
        return jsonify(result)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@bp.post("/commit")
@jwt_required()
def commit():
    uid = int(get_jwt_identity())
    data = request.get_json() or {}
    rows = data.get("transactions")
    if not rows:
        return jsonify(error="transactions required"), 400
    result = commit_normalization(uid, rows)
    return jsonify(result), 201
