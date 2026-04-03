from flask import Blueprint, request, jsonify, g
from datetime import datetime
from ..services.dynamic_budget import DynamicBudgetService
from ..middleware.auth import require_auth

budget_bp = Blueprint("dynamic_budget", __name__)
svc = DynamicBudgetService()

@budget_bp.route("/api/budgets/suggestions", methods=["GET"])
@require_auth
def get_suggestions():
    """Get AI-powered budget suggestions based on spending history."""
    user_id = g.user_id
    income = request.args.get("monthly_income")
    income_float = float(income) if income else None
    result = svc.suggest_budgets(user_id, monthly_income=income_float)
    return jsonify(result)

@budget_bp.route("/api/budgets", methods=["GET"])
@require_auth
def get_budgets():
    """Get all set budgets for the user."""
    user_id = g.user_id
    budgets = svc.get_budgets(user_id)
    return jsonify({"budgets": budgets})

@budget_bp.route("/api/budgets", methods=["POST"])
@require_auth
def set_budget():
    """Set a budget for a category."""
    user_id = g.user_id
    data = request.get_json() or {}
    category = data.get("category", "").strip()
    amount = data.get("amount")
    if not category or amount is None:
        return jsonify({"error": "category and amount required"}), 400
    result = svc.set_budget(user_id, category, float(amount))
    return jsonify(result), 201

@budget_bp.route("/api/budgets/status", methods=["GET"])
@require_auth
def budget_status():
    """Get current month budget vs actual spending status."""
    user_id = g.user_id
    now = datetime.utcnow()
    year = int(request.args.get("year", now.year))
    month = int(request.args.get("month", now.month))
    statuses = svc.check_budget_status(user_id, year, month)
    return jsonify({"statuses": statuses, "month": month, "year": year})