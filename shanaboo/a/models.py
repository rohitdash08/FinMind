from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy.dialects.postgresql import ARRAY

db = SQLAlchemy()

    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    kyc_verified = db.Column(db.Boolean, default=False)
    
    transactions = db.relationship('Transaction', backref='user', lazy=True)
    
            'balance': float(self.balance),
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'kyc_verified': self.kyc_verified
        }

class Transaction(db.Model):
            'amount': float(self.amount),
            'status': self.status,
            'created_at': self.created_at.isoformat()
        }

class WebhookEndpoint(db.Model):
    __tablename__ = 'webhook_endpoints'
    
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    event_types = db.Column(ARRAY(db.String), nullable=False)
    secret = db.Column(db.String(255))  # Optional: for endpoint verification
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    deliveries = db.relationship('WebhookDelivery', backref='endpoint', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'url': self.url,
            'description': self.description,
            'is_active': self.is_active,
            'event_types': self.event_types,
            'created_at': self.created_at.isoformat()
        }

class WebhookDelivery(db.Model):
    __tablename__ = 'webhook_deliveries'
    
    id = db.Column(db.Integer, primary_key=True)
    endpoint_id = db.Column(db.Integer, db.ForeignKey('webhook_endpoints.id'), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, delivered, failed, retrying
    status_code = db.Column(db.Integer)
    response_body = db.Column(db.Text)
    failure_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime)
    
    def to_dict(self):
        return {
            'id': self.id,
            'endpoint_id': self.endpoint_id,
            'event_type': self.event_type,
            'payload': self.payload,
            'status': self.status,
            'status_code': self.status_code,
            'response_body': self.response_body,
            'failure_reason': self.failure_reason,
            'created_at': self.created_at.isoformat(),
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None
        }