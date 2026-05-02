from datetime import datetime, timedelta
from sqlalchemy import func
from ..extensions import db
from ..models import ReminderDelivery, ReminderDeliveryStatus
from ..observability import track_reminder_event


class DeliveryTracker:
  """Track reminder delivery reliability and metrics."""

  def record_attempt(self, reminder_id: int, channel: str, status: str, error: str | None = None) -> ReminderDelivery:
    """Record a delivery attempt."""
    delivery = ReminderDelivery.query.filter_by(reminder_id=reminder_id).first()
    if not delivery:
      delivery = ReminderDelivery(
        reminder_id=reminder_id,
        channel=channel,
        attempts=0,
      )
      db.session.add(delivery)

    delivery.attempts = (delivery.attempts or 0) + 1
    delivery.status = status
    delivery.last_error = error
    if status == ReminderDeliveryStatus.DELIVERED.value:
      delivery.delivered_at = datetime.utcnow()

    db.session.commit()

    # Track in Prometheus
    track_reminder_event("delivery_attempt", channel, status)

    return delivery

  def get_delivery_stats(self, user_id: int | None = None, days: int = 30) -> dict:
    """Get delivery statistics."""
    since = datetime.utcnow() - timedelta(days=days)
    query = ReminderDelivery.query.filter(ReminderDelivery.created_at >= since)

    if user_id is not None:
      from ..models import Reminder
      query = query.join(Reminder, ReminderDelivery.reminder_id == Reminder.id).filter(Reminder.user_id == user_id)

    total = query.count()
    delivered = query.filter(ReminderDelivery.status == ReminderDeliveryStatus.DELIVERED.value).count()
    failed = query.filter(ReminderDelivery.status.in_([
      ReminderDeliveryStatus.FAILED.value,
      ReminderDeliveryStatus.BOUNCED.value,
    ])).count()

    avg_query = db.session.query(func.avg(ReminderDelivery.attempts)).filter(
      ReminderDelivery.created_at >= since
    )
    if user_id is not None:
      from ..models import Reminder
      avg_query = avg_query.join(Reminder, ReminderDelivery.reminder_id == Reminder.id).filter(Reminder.user_id == user_id)
    avg_attempts = avg_query.scalar() or 0

    return {
      "total": total,
      "delivered": delivered,
      "failed": failed,
      "success_rate": round((delivered / total * 100), 2) if total > 0 else 0,
      "avg_attempts": round(float(avg_attempts), 2),
    }

  def get_channel_stats(self, days: int = 30) -> dict:
    """Get stats broken down by channel."""
    since = datetime.utcnow() - timedelta(days=days)
    results = db.session.query(
      ReminderDelivery.channel,
      ReminderDelivery.status,
      func.count(ReminderDelivery.id),
    ).filter(
      ReminderDelivery.created_at >= since
    ).group_by(
      ReminderDelivery.channel, ReminderDelivery.status
    ).all()

    stats: dict = {}
    for channel, status, count in results:
      if channel not in stats:
        stats[channel] = {"total": 0, "delivered": 0, "failed": 0}
      stats[channel]["total"] += count
      if status == ReminderDeliveryStatus.DELIVERED.value:
        stats[channel]["delivered"] += count
      elif status in [ReminderDeliveryStatus.FAILED.value, ReminderDeliveryStatus.BOUNCED.value]:
        stats[channel]["failed"] += count

    return stats

  def get_delivery_history(self, user_id: int | None = None, page: int = 1, page_size: int = 20) -> tuple[list[ReminderDelivery], int]:
    """Get paginated delivery history."""
    query = ReminderDelivery.query

    if user_id is not None:
      from ..models import Reminder
      query = query.join(Reminder, ReminderDelivery.reminder_id == Reminder.id).filter(Reminder.user_id == user_id)

    total = query.count()
    items = (
      query.order_by(ReminderDelivery.created_at.desc())
      .offset((page - 1) * page_size)
      .limit(page_size)
      .all()
    )
    return items, total


delivery_tracker = DeliveryTracker()
