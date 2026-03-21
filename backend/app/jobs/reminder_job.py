from flask import current_app
from ..extensions import db
from ..models import Reminder
from datetime import datetime

def run():
    current_app.logger.info("Running reminder job...")
    now = datetime.utcnow()
    reminders = Reminder.query.filter(Reminder.due_date <= now, Reminder.sent == False).all()
    for reminder in reminders:
        try:
            # Logic to send reminder (e.g., via email or SMS)
            reminder.sent = True
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to send reminder {reminder.id}: {e}")