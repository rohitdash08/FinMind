from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

    channel = db.Column(db.String(50), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<AuditLog {self.id}: {self.action} by {self.user_id} at {self.timestamp}>"

    def to_dict(self):
        return {"id": self.id, "user_id": self.user_id, "action": self.action, "timestamp": self.timestamp.isoformat()}