"""Subscription detection and cost monitoring models for FinMind.

Auto-detects recurring charges as subscriptions and monitors cost changes.
"""

from datetime import datetime, timezone
from ..extensions import db


class DetectedSubscription(db.Model):
    """Auto-detected subscription from recurring transactions."""
    __tablename__ = "detected_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    merchant = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(100), nullable=True)
    amount = db.Column(db.Float, nullable=False)
    original_amount = db.Column(db.Float, nullable=True)  # First detected amount
    currency = db.Column(db.String(3), default="USD")
    frequency = db.Column(db.String(20), default="monthly")  # weekly, monthly, yearly
    confidence = db.Column(db.Float, default=0.0)  # 0-1 detection confidence
    occurrence_count = db.Column(db.Integer, default=1)
    first_seen = db.Column(db.DateTime, nullable=True)
    last_seen = db.Column(db.DateTime, nullable=True)
    next_expected = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_confirmed = db.Column(db.Boolean, default=False)  # User confirmed
    tags = db.Column(db.String(500), nullable=True)  # Comma-separated tags
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        cost_change = None
        if self.original_amount and self.amount != self.original_amount:
            diff = self.amount - self.original_amount
            cost_change = {
                "original": self.original_amount,
                "current": self.amount,
                "difference": round(diff, 2),
                "percentage": round((diff / self.original_amount) * 100, 1) if self.original_amount else 0,
            }

        return {
            "id": self.id,
            "merchant": self.merchant,
            "category": self.category,
            "amount": self.amount,
            "original_amount": self.original_amount,
            "currency": self.currency,
            "frequency": self.frequency,
            "confidence": round(self.confidence, 3),
            "occurrence_count": self.occurrence_count,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "next_expected": self.next_expected.isoformat() if self.next_expected else None,
            "is_active": self.is_active,
            "is_confirmed": self.is_confirmed,
            "tags": self.tags.split(",") if self.tags else [],
            "cost_change": cost_change,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class SubscriptionCostAlert(db.Model):
    """Alert when subscription cost increases."""
    __tablename__ = "subscription_cost_alerts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    subscription_id = db.Column(db.Integer, db.ForeignKey("detected_subscriptions.id"), nullable=False)
    merchant = db.Column(db.String(200), nullable=False)
    old_amount = db.Column(db.Float, nullable=False)
    new_amount = db.Column(db.Float, nullable=False)
    increase_percentage = db.Column(db.Float, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "subscription_id": self.subscription_id,
            "merchant": self.merchant,
            "old_amount": self.old_amount,
            "new_amount": self.new_amount,
            "increase_percentage": round(self.increase_percentage, 1),
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
