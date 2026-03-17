"""
Webhook models — appended to main models via import in app factory.
Kept separate to keep the diff clean.
"""
from datetime import datetime
from .extensions import db


class Webhook(db.Model):
    __tablename__ = "webhooks"
    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    url         = db.Column(db.String(2048), nullable=False)
    secret      = db.Column(db.String(256), nullable=False)
    events      = db.Column(db.Text, nullable=False, default="[]")   # JSON list
    active      = db.Column(db.Boolean, default=True, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)
    deliveries  = db.relationship("WebhookDelivery", backref="webhook",
                                  cascade="all, delete-orphan", lazy="dynamic")


class WebhookDelivery(db.Model):
    __tablename__ = "webhook_deliveries"
    id            = db.Column(db.Integer, primary_key=True)
    webhook_id    = db.Column(db.Integer, db.ForeignKey("webhooks.id"), nullable=False)
    event_type    = db.Column(db.String(100), nullable=False)
    payload       = db.Column(db.Text, nullable=False)   # JSON blob
    attempt       = db.Column(db.SmallInteger, default=1, nullable=False)
    status        = db.Column(db.String(20), default="pending", nullable=False)
    response_code = db.Column(db.SmallInteger, nullable=True)
    response_body = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    delivered_at  = db.Column(db.DateTime, nullable=True)
    next_retry_at = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
