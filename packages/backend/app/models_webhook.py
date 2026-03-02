"""Webhook models for FinMind."""
from datetime import datetime
from enum import Enum
from sqlalchemy import Enum as SAEnum
from .extensions import db


class WebhookEventType(str, Enum):
    """Supported webhook event types."""
    EXPENSE_CREATED = "expense.created"
    EXPENSE_UPDATED = "expense.updated"
    EXPENSE_DELETED = "expense.deleted"
    BILL_CREATED = "bill.created"
    BILL_UPDATED = "bill.updated"
    BILL_DUE = "bill.due"
    RECURRING_EXPENSE_CREATED = "recurring_expense.created"
    RECURRING_EXPENSE_TRIGGERED = "recurring_expense.triggered"
    USER_SUBSCRIPTION_CREATED = "user_subscription.created"
    USER_SUBSCRIPTION_CANCELLED = "user_subscription.cancelled"


class WebhookStatus(str, Enum):
    """Webhook subscription status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"


class WebhookSubscription(db.Model):
    """User webhook subscriptions."""
    __tablename__ = "webhook_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url = db.Column(db.String(2048), nullable=False)
    secret = db.Column(db.String(255), nullable=False)  # For HMAC signature
    events = db.Column(db.JSON, nullable=False)  # List of event types
    status = db.Column(SAEnum(WebhookStatus), default=WebhookStatus.ACTIVE, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    failure_count = db.Column(db.Integer, default=0, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "events": self.events,
            "status": self.status.value,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "failure_count": self.failure_count,
        }


class WebhookDeliveryStatus(str, Enum):
    """Webhook delivery attempt status."""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class WebhookDelivery(db.Model):
    """Webhook delivery attempts log."""
    __tablename__ = "webhook_deliveries"

    id = db.Column(db.Integer, primary_key=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("webhook_subscriptions.id"), nullable=False)
    event_type = db.Column(db.String(100), nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    status = db.Column(SAEnum(WebhookDeliveryStatus), default=WebhookDeliveryStatus.PENDING, nullable=False)
    response_status_code = db.Column(db.Integer, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    scheduled_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    delivered_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "subscription_id": self.subscription_id,
            "event_type": self.event_type,
            "status": self.status.value,
            "response_status_code": self.response_status_code,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
