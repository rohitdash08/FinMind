from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, current_user
from app.extensions import db
from app.models import Expense, Category
from datetime import date
from sqlalchemy.exc import IntegrityError

expenses_bp = Blueprint("expenses", __name__, url_prefix="/expenses")

@expenses_bp.route("", methods=["POST"])
@jwt_required()
def create_expense():
    """Create a new expense."""
    data = request.get_json()
    amount = data.get("amount")
    description = data.get("description")
    expense_date_str = data.get("date")
    expense_type = data.get("expense_type", "EXPENSE")
    category_name = data.get("category_name")

    if not all([amount, description, expense_date_str]):
        return jsonify({"message": "Amount, description, and date are required"}), 400

    try:
        expense_date = date.fromisoformat(expense_date_str)
        amount = float(amount)
        if amount <= 0:
            return jsonify({"message": "Amount must be positive"}), 400
    except ValueError:
        return jsonify({"message": "Invalid amount or date format"}), 400

    category_id = None
    if category_name:
        category = Category.query.filter_by(user_id=current_user.id, name=category_name).first()
        if not category:
            return jsonify({"message": f"Category '{category_name}' not found"}), 404
        category_id = category.id

    new_expense = Expense(
        user_id=current_user.id,
        amount=amount,
        description=description,
        date=expense_date,
        expense_type=expense_type,
        currency=current_user.preferred_currency,
        category_id=category_id
    )

    try:
        db.session.add(new_expense)
        db.session.commit()
        return jsonify({
            "id": new_expense.id,
            "amount": float(new_expense.amount),
            "description": new_expense.description,
            "date": new_expense.date.isoformat(),
            "currency": new_expense.currency,
            "expense_type": new_expense.expense_type,
            "category_id": new_expense.category_id,
        }), 201
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "Error creating expense"}), 500

@expenses_bp.route("", methods=["GET"])
@jwt_required()
def list_expenses():
    """List all expenses for the current user."""
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    result = []
    for expense in expenses:
        result.append({
            "id": expense.id,
            "amount": float(expense.amount),
            "description": expense.description,
            "date": expense.date.isoformat(),
            "currency": expense.currency,
            "expense_type": expense.expense_type,
            "category_id": expense.category_id,
            "category_name": expense.category.name if expense.category else None,
        })
    return jsonify(result), 200

