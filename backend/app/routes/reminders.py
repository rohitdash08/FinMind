from flask import Blueprint, jsonify, request
from ..extensions import db
from ..extensions import scheduler
from ..models import Reminder

reminders_bp = Blueprint('reminders', __name__)
    db.session.commit()
    return jsonify(reminder.to_dict()), 201

@reminders_bp.route('/run', methods=['POST'])
def run_reminders():
    reminders = Reminder.query.all()
    for reminder in reminders:
        if reminder.is_due():
            send_reminder(reminder)
    return jsonify({"message": "Reminders processed"}), 200

def send_reminder(reminder):
    # Logic to send reminder via email or WhatsApp
    print(f"Sending reminder: {reminder.message}")

def schedule_reminder_jobs():
    scheduler.add_job(run_reminders, CronTrigger.from_crontab('0 * * * *'))  # Every hour