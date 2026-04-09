from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, webhook_logger
from app.models import Bill, User
from datetime import datetime
from app.services.cache import invalidate_cache
from app.services.webhooks import emit_event # New import

bills_bp = Blueprint('bills', __name__)        db.session.add(new_bill)
        db.session.commit()
        invalidate_cache(user.id, ['upcoming_bills'])

        # Emit webhook event
        try:
            emit_event(user.id, 'bill.created', new_bill.to_dict())
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'bill.created' webhook for user {user.id}: {e}")

        return jsonify(new_bill.to_dict()), 201        bill.name = data.get('name', bill.name)
        bill.amount = data.get('amount', bill.amount)
        bill.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d').date() if 'due_date' in data else bill.due_date
        bill.is_paid = data.get('is_paid', bill.is_paid)
        bill.cadence = data.get('cadence', bill.cadence)
        bill.payment_channel = data.get('payment_channel', bill.payment_channel)
        db.session.commit()
        invalidate_cache(user.id, ['upcoming_bills'])

        # Emit webhook event
        try:
            emit_event(user.id, 'bill.updated', bill.to_dict())
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'bill.updated' webhook for user {user.id}: {e}")

        return jsonify(bill.to_dict())        bill_data = bill.to_dict() # Capture data before deletion
        db.session.delete(bill)
        db.session.commit()
        invalidate_cache(user.id, ['upcoming_bills'])
        
        # Emit webhook event
        try:
            emit_event(user.id, 'bill.deleted', bill_data)
        except Exception as e:
            webhook_logger.error(f"Failed to emit 'bill.deleted' webhook for user {user.id}: {e}")

        return jsonify({"message": "Bill deleted"}), 204    bill.is_paid = True
    db.session.commit()
    invalidate_cache(user.id, ['upcoming_bills'])

    # Emit webhook event
    try:
        emit_event(user.id, 'bill.paid', bill.to_dict())
    except Exception as e:
        webhook_logger.error(f"Failed to emit 'bill.paid' webhook for user {user.id}: {e}")

    return jsonify(bill.to_dict())