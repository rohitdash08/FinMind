"""
Weekly Digest API Routes

Endpoints for generating and retrieving weekly financial summaries.
"""

from datetime import date, datetime, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity

from ..services.digest import WeeklyDigestService
from ..models import User
from ..extensions import db
import logging

bp = Blueprint("digest", __name__)
logger = logging.getLogger("finmind.digest")


@bp.get("/weekly")
@jwt_required()
def get_weekly_digest():
    """
    Get the weekly financial digest for the current user.

    Query params:
        week_start: Optional ISO date string (YYYY-MM-DD) for the start of the week.
                   Defaults to the current week's Monday.

    Returns:
        JSON object containing:
        - period: Week start/end dates
        - summary: Income, expenses, net flow, savings rate
        - trends: Week-over-week changes
        - spending_by_category: Category breakdown with percentages
        - notable_transactions: Top transactions by amount
        - upcoming_bills: Bills due in the next 7 days
        - insights: Actionable financial insights
    """
    uid = int(get_jwt_identity())

    # Parse optional week_start parameter
    week_start_param = request.args.get("week_start", "").strip()

    try:
        if week_start_param:
            week_start = date.fromisoformat(week_start_param)
            # Ensure week_start is a Monday
            days_since_monday = week_start.weekday()
            if days_since_monday != 0:
                week_start = week_start - timedelta(days=days_since_monday)
            week_end = week_start + timedelta(days=6)
        else:
            week_start, week_end = WeeklyDigestService.get_week_bounds()
    except ValueError:
        return jsonify(error="Invalid week_start format. Use YYYY-MM-DD."), 400

    try:
        summary = WeeklyDigestService.generate_weekly_summary(
            uid, week_start, week_end
        )
        logger.info("Weekly digest generated for user %s", uid)
        return jsonify(summary)

    except Exception as e:
        logger.error("Error generating weekly digest: %s", str(e))
        return jsonify(error="Failed to generate weekly digest"), 500


@bp.post("/weekly/send")
@jwt_required()
def send_weekly_digest():
    """
    Send the weekly digest email to the current user.

    Returns:
        JSON object with success status and message.
    """
    uid = int(get_jwt_identity())

    try:
        user = db.session.get(User, uid)
        if not user:
            return jsonify(error="User not found"), 404

        week_start, week_end = WeeklyDigestService.get_week_bounds()
        summary = WeeklyDigestService.generate_weekly_summary(
            uid, week_start, week_end
        )

        if summary["summary"]["transaction_count"] == 0:
            return jsonify(
                success=False,
                message="No transactions this week. Email not sent."
            ), 200

        success = WeeklyDigestService.send_digest_email(uid, summary)

        if success:
            logger.info("Weekly digest email sent to user %s", uid)
            return jsonify(
                success=True,
                message="Weekly digest email sent successfully."
            ), 200
        else:
            return jsonify(
                success=False,
                message="Failed to send email. Please check your email settings."
            ), 500

    except Exception as e:
        logger.error("Error sending weekly digest: %s", str(e))
        return jsonify(error="Failed to send weekly digest"), 500


@bp.get("/weekly/preview")
@jwt_required()
def preview_weekly_digest():
    """
    Preview the weekly digest email content.

    Returns:
        JSON object with subject and body of the email.
    """
    uid = int(get_jwt_identity())

    try:
        user = db.session.get(User, uid)
        if not user:
            return jsonify(error="User not found"), 404

        week_start, week_end = WeeklyDigestService.get_week_bounds()
        summary = WeeklyDigestService.generate_weekly_summary(
            uid, week_start, week_end
        )

        subject, body = WeeklyDigestService.format_digest_email(summary, user)

        return jsonify(
            subject=subject,
            body=body,
            summary=summary,
        ), 200

    except Exception as e:
        logger.error("Error previewing weekly digest: %s", str(e))
        return jsonify(error="Failed to preview weekly digest"), 500

