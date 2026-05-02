"""
Login anomaly detection service.
Analyzes login patterns and generates alerts for suspicious activity.
"""
from datetime import datetime, timedelta
from ..extensions import db
from ..models_login import LoginEvent, LoginAlert

RAPID_ATTEMPTS_THRESHOLD = 5
RAPID_ATTEMPTS_WINDOW_MINUTES = 15
UNUSUAL_HOUR_START = 2
UNUSUAL_HOUR_END = 5


def record_login(user_id, ip_address=None, user_agent=None, location=None, success=True):
    event = LoginEvent(
        user_id=user_id, ip_address=ip_address,
        user_agent=user_agent, location=location, success=success,
    )
    db.session.add(event)
    db.session.flush()
    if success:
        _check_new_device(user_id, event)
        _check_new_location(user_id, event)
        _check_unusual_time(user_id, event)
    else:
        _check_rapid_failed_attempts(user_id, event)
    db.session.commit()
    return event


def _check_new_device(user_id, event):
    if not event.user_agent:
        return
    existing = LoginEvent.query.filter(
        LoginEvent.user_id == user_id, LoginEvent.user_agent == event.user_agent,
        LoginEvent.id != event.id, LoginEvent.success == True,
    ).first()
    if not existing:
        db.session.add(LoginAlert(
            user_id=user_id, alert_type="new_device",
            message=f"Login from new device: {event.user_agent[:100]}",
            severity="medium", login_event_id=event.id,
        ))


def _check_new_location(user_id, event):
    if not event.location:
        return
    existing = LoginEvent.query.filter(
        LoginEvent.user_id == user_id, LoginEvent.location == event.location,
        LoginEvent.id != event.id, LoginEvent.success == True,
    ).first()
    if not existing:
        db.session.add(LoginAlert(
            user_id=user_id, alert_type="new_location",
            message=f"Login from new location: {event.location}",
            severity="medium", login_event_id=event.id,
        ))


def _check_rapid_failed_attempts(user_id, event):
    window_start = datetime.utcnow() - timedelta(minutes=RAPID_ATTEMPTS_WINDOW_MINUTES)
    count = LoginEvent.query.filter(
        LoginEvent.user_id == user_id, LoginEvent.success == False,
        LoginEvent.created_at >= window_start,
    ).count()
    if count >= RAPID_ATTEMPTS_THRESHOLD:
        db.session.add(LoginAlert(
            user_id=user_id, alert_type="rapid_attempts",
            message=f"{count} failed login attempts in {RAPID_ATTEMPTS_WINDOW_MINUTES} minutes",
            severity="high", login_event_id=event.id,
        ))


def _check_unusual_time(user_id, event):
    hour = event.created_at.hour
    if UNUSUAL_HOUR_START <= hour < UNUSUAL_HOUR_END:
        db.session.add(LoginAlert(
            user_id=user_id, alert_type="unusual_time",
            message=f"Login at unusual time: {event.created_at.strftime('%H:%M')}",
            severity="low", login_event_id=event.id,
        ))


def get_user_alerts(user_id, unread_only=False):
    query = LoginAlert.query.filter_by(user_id=user_id)
    if unread_only:
        query = query.filter_by(is_read=False)
    return query.order_by(LoginAlert.created_at.desc()).limit(50).all()


def mark_alerts_read(user_id, alert_ids=None):
    query = LoginAlert.query.filter_by(user_id=user_id, is_read=False)
    if alert_ids:
        query = query.filter(LoginAlert.id.in_(alert_ids))
    query.update({"is_read": True}, synchronize_session=False)
    db.session.commit()


def get_login_history(user_id, limit=20):
    return LoginEvent.query.filter_by(user_id=user_id, success=True).order_by(
        LoginEvent.created_at.desc()
    ).limit(limit).all()
