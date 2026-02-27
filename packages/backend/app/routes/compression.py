"""API compression stats & optimization API."""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required
from ..services.compression import get_compression_stats

bp = Blueprint("compression", __name__)


@bp.get("/stats")
@jwt_required()
def stats():
    return jsonify(get_compression_stats())
