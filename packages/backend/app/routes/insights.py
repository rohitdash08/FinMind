from datetime import date, timedelta
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, current_user
from sqlalchemy import func, extract
from app.extensions import db
from app.models import Expense

insights_bp = Blueprint("insights", __name__, url_prefix="/insights")

@insights_bp.route("/spending-heatmap", methods=["GET"])
@jwt_required()
def get_spending_heatmap():
    """
    Returns aggregated spending data for a heatmap visualization.
    Filters by user and date range, then aggregates by date.
    Query parameters:
        start_date (str, YYYY-MM-DD): The start date for the data. Required.
        end_date (str, YYYY-MM-DD): The end date for the data. Required.
    """
    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")

    if not start_date_str or not end_date_str:
        return jsonify({"message": "start_date and end_date are required"}), 400

    try:
        start_date = date.fromisoformat(start_date_str)
        end_date = date.fromisoformat(end_date_str)
    except ValueError:
        return jsonify({"message": "Invalid date format. Use YYYY-MM-DD"}), 400

    if start_date > end_date:
        return jsonify({"message": "start_date cannot be after end_date"}), 400

    query = (
        db.session.query(
            Expense.date,
            func.sum(Expense.amount).label("total_amount")
        )
        .filter(Expense.user_id == current_user.id)
        .filter(Expense.date >= start_date)
        .filter(Expense.date <= end_date)
        .group_by(Expense.date)
        .order_by(Expense.date)
    )

    results = query.all()

    heatmap_data = [
        {"date": row.date.isoformat(), "total_amount": float(row.total_amount)}
        for row in results
    ]

    return jsonify(heatmap_data), 200

