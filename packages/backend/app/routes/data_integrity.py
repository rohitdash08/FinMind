from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..services.data_integrity import get_data_integrity_report

bp = Blueprint("data_integrity", __name__)


@bp.route("/reconciliation", methods=["GET"])
@jwt_required()
def reconciliation_report():
    """
    GET /insights/reconciliation
    Query params:
      - months: int (1-24, default 6)
    Returns a full data integrity report with issues and summary.
    """
    user_id = get_jwt_identity()
    try:
        months = int(request.args.get("months", 6))
    except (ValueError, TypeError):
        return jsonify({"error": "months must be an integer"}), 400

    result = get_data_integrity_report(user_id, months)
    return jsonify({
        "summary": result.summary,
        "months_checked": result.months_checked,
        "checked_at": result.checked_at,
        "issues": [
            {
                "type": issue.issue_type,
                "severity": issue.severity,
                "record_type": issue.record_type,
                "record_id": issue.record_id,
                "description": issue.description,
                "details": issue.details,
            }
            for issue in result.issues
        ],
    })