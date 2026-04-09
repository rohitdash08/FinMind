from datetime import datetime
from app.extensions import db
from sqlalchemy.dialects.postgresql import JSONB
import uuid

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='user')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    webhook_endpoints = db.relationship('WebhookEndpoint', backref='user', lazy=True, cascade='all, delete-orphan')

class WebhookEndpoint(db.Model):
    __tablename__ = 'webhook_endpoints'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    secret = db.Column(db.String(255), nullable=False)
    event_types = db.Column(JSONB, default=[]) # JSON array of event types
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    delivery_attempts = db.relationship('WebhookDeliveryAttempt', backref='endpoint', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'url': self.url,
            'event_types': self.event_types,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class WebhookDeliveryAttempt(db.Model):
    __tablename__ = 'webhook_delivery_attempts'
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('webhook_endpoints.id', ondelete='CASCADE'), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    event_id = db.Column(db.String(36), default=lambda: str(uuid.uuid4()), nullable=False) # UUID for the specific event instance
    payload = db.Column(db.Text, nullable=False) # JSON payload as string
    attempt_number = db.Column(db.Integer, default=1)
    status_code = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    error_message = db.Column(db.Text)
    next_attempt_at = db.Column(db.DateTime)
    is_successful = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'event_type': self.event_type,
            'event_id': self.event_id,
            'attempt_number': self.attempt_number,
            'status_code': self.status_code,
            'is_successful': self.is_successful,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }