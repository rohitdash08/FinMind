"""Weekly digest route."""

import re
from datetime import date
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.digest import weekly_digest
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")

_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


@bp.get("/weekly")
@jwt_required()
def weekly():
    uid = int(get_jwt_identity())
    week_param = request.args.get("week")

    if week_param:
        m = _WEEK_RE.match(week_param)
        if not m:
            return jsonify(error="Invalid week format. Use YYYY-WNN."), 400
        year, week_num = int(m.group(1)), int(m.group(2))
        if week_num < 1 or week_num > 53:
            return jsonify(error="Week number must be between 01 and 53."), 400
    else:
        today = date.today()
        year, week_num, _ = today.isocalendar()

    result = weekly_digest(uid, year, week_num)
    logger.info("Weekly digest served user=%s week=%s-W%02d", uid, year, week_num)
    return jsonify(result)
