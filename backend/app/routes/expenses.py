from flask import Blueprint, request, jsonify
from flask_webhook import emit_event
from backend.app.models import Expense, db

bp = Blueprint('expenses', __name__)
    db.session.commit()
    return jsonify(expense.to_dict()), 201
    emit_event('expense_created', expense)

@bp.route('/expenses/<int:expense_id>', methods=['GET'])
def get_expense(expense_id):