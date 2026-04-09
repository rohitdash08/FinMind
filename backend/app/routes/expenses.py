from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, webhook_logger
from app.models import Expense, User, Category
from datetime import datetime
from app.services.cache import invalidate_cache
from app.services.webhooks import emit_event # New import

expenses_bp = Blueprint('expenses', __name__)        db.session.add(new_expense)
        db.session.commit()
        invalidate_cache(user.id, ['monthly_summary', 'insights'])
        
        # Emit webhook event
        try:
            emit_event(user.id, 'expense.created', new_expense.to_dict())
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'expense.created' webhook for user {user.id}: {e}")

        return jsonify(new_expense.to_dict()), 201        expense.description = data.get('description', expense.description)
        expense.category_id = data.get('category_id', expense.category_id)
        expense.date = datetime.strptime(data['date'], '%Y-%m-%d').date() if 'date' in data else expense.date
        db.session.commit()
        invalidate_cache(user.id, ['monthly_summary', 'insights'])

        # Emit webhook event
        try:
            emit_event(user.id, 'expense.updated', expense.to_dict())
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'expense.updated' webhook for user {user.id}: {e}")

        return jsonify(expense.to_dict())        expense_data = expense.to_dict() # Capture data before deletion
        db.session.delete(expense)
        db.session.commit()
        invalidate_cache(user.id, ['monthly_summary', 'insights'])

        # Emit webhook event
        try:
            emit_event(user.id, 'expense.deleted', expense_data)
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'expense.deleted' webhook for user {user.id}: {e}")

        return jsonify({"message": "Expense deleted"}), 204