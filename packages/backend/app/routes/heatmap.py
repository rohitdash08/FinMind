"""Calendar heatmap endpoint for FinMind."""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.heatmap import get_heatmap_data

bp = Blueprint("heatmap", __name__)


@bp.get("")
@jwt_required()
def heatmap():
    """Get calendar heatmap data.

    Query params:
        year (int): Required. Year to fetch.
        month (int): Optional. Month (1-12). If omitted, returns full year.
    """
    uid = int(get_jwt_identity())

    try:
        year = int(request.args.get("year"))
    except (TypeError, ValueError):
        return jsonify(error="year query parameter is required"), 400

    month = request.args.get("month")
    if month:
        try:
            month = int(month)
            if not 1 <= month <= 12:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify(error="month must be between 1 and 12"), 400
    else:
        month = None

    data = get_heatmap_data(uid, year, month)
    return jsonify(data)
