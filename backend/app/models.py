from datetime import datetime
from flask_webhook import emit_event
from backend.app import db

class Expense(db.Model):
        db.session.add(self)
        db.session.commit()
        emit_event('expense_created', self)

    def to_dict(self):
        return {
        db.session.add(self)
        db.session.commit()
        emit_event('bill_created', self)

    def to_dict(self):
        return {