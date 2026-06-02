"""
Reminder reliability tracking and delivery metrics.
"""
from datetime import datetime, timedelta
from ..extensions import db


class ReminderDelivery(db.Model):
    __tablename__ = "reminder_deliveries"
    
    id = db.Column(db.Integer, primary_key=True)
    reminder_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    channel = db.Column(db.String(20), nullable=False)  # email, push, sms
    status = db.Column(db.String(20), nullable=False)  # sent, delivered, failed
    latency_ms = db.Column(db.Integer, nullable=True)
    error = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Add index for faster queries
    __table_args__ = (
        db.Index('idx_user_created', 'user_id', 'created_at'),
    )


def track_delivery(reminder_id: int, user_id: int, channel: str, status: str, latency_ms: int = None, error: str = None):
    """Track a reminder delivery attempt."""
    delivery = ReminderDelivery(
        reminder_id=reminder_id,
        user_id=user_id,
        channel=channel,
        status=status,
        latency_ms=latency_ms,
        error=error,
    )
    db.session.add(delivery)
    db.session.commit()


def get_delivery_metrics(user_id: int, days: int = 30) -> dict:
    """Get delivery reliability metrics."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    deliveries = ReminderDelivery.query.filter(
        ReminderDelivery.user_id == user_id,
        ReminderDelivery.created_at > cutoff
    ).all()
    
    total = len(deliveries)
    if total == 0:
        return {
            "total": 0, 
            "success_rate": 0, 
            "avg_latency_ms": 0,
            "by_channel": {}
        }
    
    successful = len([d for d in deliveries if d.status in ("sent", "delivered")])
    latencies = [d.latency_ms for d in deliveries if d.latency_ms is not None]
    
    # Calculate by_channel breakdown
    by_channel = {}
    for channel in set(d.channel for d in deliveries):
        channel_deliveries = [d for d in deliveries if d.channel == channel]
        channel_successful = len([d for d in channel_deliveries if d.status in ("sent", "delivered")])
        channel_latencies = [d.latency_ms for d in channel_deliveries if d.latency_ms is not None]
        
        by_channel[channel] = {
            "total": len(channel_deliveries),
            "success_rate": channel_successful / len(channel_deliveries) * 100 if channel_deliveries else 0,
            "avg_latency_ms": sum(channel_latencies) / len(channel_latencies) if channel_latencies else 0,
        }
    
    return {
        "total": total,
        "success_rate": successful / total * 100,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "by_channel": by_channel,
    }
