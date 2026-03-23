from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import User, Expense, Bill

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.route('/overview', methods=['GET'])
@jwt_required()
def get_financial_overview():
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        return jsonify({"message": "User not found"}), 404

    expenses = Expense.query.filter_by(user_id=user_id).all()
    bills = Bill.query.filter_by(user_id=user_id).all()

    total_expenses = sum(expense.amount for expense in expenses)
    total_bills = sum(bill.amount for bill in bills)

    return jsonify({
        "user": user.username,
        "total_expenses": total_expenses,
        "total_bills": total_bills,
        "accounts": [
            {"name": "Main Account", "expenses": total_expenses, "bills": total_bills}
            # Add more accounts as needed
        ]
    }), 200