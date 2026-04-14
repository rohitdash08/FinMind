from datetime import date

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import generate_weekly_digest, send_weekly_digest_email

bp = Blueprint("digest", __name__)


@bp.get("/weekly")
@jwt_required()
def weekly_digest():
    """Get the weekly financial digest for the current user."""
    uid = int(get_jwt_identity())
    end_date_str = request.args.get("end_date")
    end_date = None
    if end_date_str:
        try:
            end_date = date.fromisoformat(end_date_str)
        except ValueError:
            return jsonify(error="invalid end_date, expected YYYY-MM-DD"), 400

    digest = generate_weekly_digest(uid, end_date=end_date)
    return jsonify(digest)


@bp.post("/weekly/send")
@jwt_required()
def send_digest():
    """Generate and email the weekly digest to the current user."""
    uid = int(get_jwt_identity())
    success = send_weekly_digest_email(uid)
    if success:
        return jsonify(status="sent")
    return jsonify(status="failed", error="could not send digest email"), 500
