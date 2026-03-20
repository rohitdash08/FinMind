from flask import Blueprint, request, jsonify
from flask_webhook import emit_event
from backend.app.models import Reminder, db

bp = Blueprint('reminders', __name__)
    db.session.commit()
    return jsonify(reminder.to_dict()), 201
    emit_event('reminder_created', reminder)

@bp.route('/reminders/<int:reminder_id>', methods=['GET'])
def get_reminder(reminder_id):