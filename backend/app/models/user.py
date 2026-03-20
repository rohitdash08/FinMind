from datetime import datetime
from flask_webhook import emit_event
from backend.app import db

class User(db.Model):
        db.session.add(self)
        db.session.commit()
        emit_event('user_created', self)

    def to_dict(self):
        return {