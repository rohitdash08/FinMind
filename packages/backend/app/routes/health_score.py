"""Health Score API route — GET /health-score"""

from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.health_score import compute_health_score

bp = Blueprint("health_score", __name__)


@bp.get("")
@jwt_required()
def health_score():
    """Return a 0-100 financial health score with breakdown and insights."""
    uid = int(get_jwt_identity())
    result = compute_health_score(uid, months=6)
    return jsonify(result)
