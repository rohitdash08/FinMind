from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from ..extensions import scheduler
from ..routes.reminders import schedule_reminder_jobs

db = SQLAlchemy()
        return {
            'id': self.id,
            'user_id': self.user_id,
            'message': self.message,
            'due_date': self.due_date.isoformat(),
            'sent': self.sent
        }

    def is_due(self):
        return datetime.utcnow() >= self.due_date

schedule_reminder_jobs()