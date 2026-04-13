"""Cash flow forecasting endpoints."""
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.forecast import forecast_cashflow
import logging

bp = Blueprint("forecast", __name__)
logger = logging.getLogger("finmind.forecast")

@bp.get("")
@jwt_required()
def get_forecast():
    uid = int(get_jwt_identity())
    months = min(int(request.args.get("months", 3)), 12)
    result = forecast_cashflow(uid, months)
    logger.info("Forecast served user=%s months=%s", uid, months)
    return jsonify(result)
