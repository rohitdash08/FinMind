from datetime import datetime
from sqlalchemy import func
from ..extensions import db
from ..models import Notification


class NotificationService:
  """Service for creating and managing notifications."""

  def create(
    self,
    user_id: int,
    title: str,
    message: str,
    priority: str = "medium",
    group: str = "system",
    action_url: str | None = None,
    metadata: dict | None = None,
  ) -> Notification:
    """Create a new notification."""
    notification = Notification(
      user_id=user_id,
      title=title,
      message=message,
      priority=priority,
      group=group,
      action_url=action_url,
      metadata_json=metadata,
    )
    db.session.add(notification)
    db.session.commit()
    return notification

  def get_user_notifications(
    self,
    user_id: int,
    unread_only: bool = False,
    group: str | None = None,
    page: int = 1,
    page_size: int = 20,
  ) -> tuple[list[Notification], int]:
    """Get notifications for a user with filtering."""
    query = Notification.query.filter_by(user_id=user_id)
    if unread_only:
      query = query.filter_by(read=False)
    if group:
      query = query.filter_by(group=group)
    total = query.count()
    items = (
      query.order_by(Notification.created_at.desc())
      .offset((page - 1) * page_size)
      .limit(page_size)
      .all()
    )
    return items, total

  def mark_read(self, notification_id: int, user_id: int) -> Notification | None:
    """Mark a notification as read."""
    n = Notification.query.filter_by(
      id=notification_id, user_id=user_id
    ).first()
    if n:
      n.read = True
      n.read_at = datetime.utcnow()
      db.session.commit()
    return n

  def mark_all_read(self, user_id: int, group: str | None = None) -> None:
    """Mark all notifications as read for a user."""
    query = Notification.query.filter_by(user_id=user_id, read=False)
    if group:
      query = query.filter_by(group=group)
    query.update({Notification.read: True, Notification.read_at: datetime.utcnow()})
    db.session.commit()

  def get_unread_count(self, user_id: int) -> dict[str, int]:
    """Get count of unread notifications by group."""
    counts = (
      db.session.query(Notification.group, func.count(Notification.id))
      .filter_by(user_id=user_id, read=False)
      .group_by(Notification.group)
      .all()
    )
    return {group: count for group, count in counts}

  def delete(self, notification_id: int, user_id: int) -> bool:
    """Delete a notification. Returns True if found and deleted."""
    n = Notification.query.filter_by(
      id=notification_id, user_id=user_id
    ).first()
    if not n:
      return False
    db.session.delete(n)
    db.session.commit()
    return True


notification_service = NotificationService()
