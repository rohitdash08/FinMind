from flask import Blueprint, request, jsonify
from flask_webhook import emit_event
from backend.app.models import Bill, db

bp = Blueprint('bills', __name__)
    db.session.commit()
    return jsonify(bill.to_dict()), 201
    emit_event('bill_created', bill)

@bp.route('/bills/<int:bill_id>', methods=['GET'])
def get_bill(bill_id):